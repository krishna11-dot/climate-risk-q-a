"""Analysis agent: generates and executes Python code against NetCDF
climate data using xarray + dask for lazy loading, producing a value,
range, and chart.

Only runs after a valid (non-coverage-gap) KG result. Code executes in
a subprocess with a hard timeout so a runaway or malicious generation
can never hang or compromise the main process.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import config
from agents import call_llm
from graph.state import ClimateRiskState
from observability.tracer import traceable

# Generated code has no legitimate need for this project's secrets
# (GROQ_API_KEY, LANGSMITH_API_KEY, DATABASE_URL, ...), but
# subprocess.run inherits the full parent environment by default —
# an unnecessary credential exposure if generated code were ever
# malicious or a code-gen bug produced something unexpected. Only the
# OS-level variables Python/xarray/matplotlib/dask genuinely need to
# run are allowed through.
_SUBPROCESS_ENV_ALLOWLIST = (
    "PATH",
    "SystemRoot",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOME",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)


def _minimal_subprocess_env() -> dict[str, str]:
    """Builds a minimal environment for the generated-code subprocess.

    Returns:
        A dict containing only the allowlisted OS-level variables
        present in the current environment — safe to pass to
        subprocess.run(..., env=...) without leaking API keys/secrets.
    """
    return {k: v for k, v in os.environ.items() if k in _SUBPROCESS_ENV_ALLOWLIST}

_CODE_GEN_PROMPT = """Generate Python code that analyses a climate NetCDF
dataset using xarray with dask lazy chunking and produces:
  1. A scalar summary value relevant to: {query}
  2. A base64-encoded PNG matplotlib chart
The dataset file path is available as the variable NETCDF_PATH (string).
Open it with:
    ds = xr.open_dataset(NETCDF_PATH, chunks={{"time": 12}})

The ACTUAL data variables in this file are (name: {{dims, dtype}}):
{data_vars}
Dimension sizes: {dims}

Use the EXACT variable name(s) shown above — never guess or invent a
different name. The hazard/variable of interest is conceptually
"{variable}"; map that to whichever of the actual variables above is
the closest match (e.g. "precipitation" -> a variable literally named
"pr"). Compute a sensible scalar summary (e.g. an overall mean, or a
mean over the final years of the time dimension) and plot a time series
or spatial map, whichever suits the available dimensions.

IMPORTANT: CMIP6 time coordinates are often cftime objects (e.g.
cftime.DatetimeNoLeap), not plain Python datetimes, and matplotlib
cannot plot them directly. `import nc_time_axis` before plotting (it
registers cftime support with matplotlib) whenever the time coordinate
is used as a plot axis — do not attempt to convert cftime values to
float manually.

IMPORTANT: Spatial coordinates (latitude especially) may be stored in
EITHER ascending or descending order depending on the source (e.g. ERA5
often runs latitude high-to-low). `.sel(coord=slice(low, high))` on a
descending coordinate silently matches ZERO points instead of raising
an error, producing a NaN result that looks like success. Before
slicing any coordinate with `.sel(slice(...))`, call
`ds = ds.sortby(coord_name)` on that coordinate first so slicing is
always safe regardless of the file's native ordering.

You have a strict output budget — keep the code SHORT:
- One straightforward approach only. No try/except fallback paths, no
  alternate isel/sel branches "just in case" — pick one indexing method
  and use it.
- Compute the scalar value and build the plot data in the SAME
  selection/slice; do not redundantly re-select or re-compute.
- No comments explaining units, methodology, or assumptions — code only.
- Prefer simple coordinate-value slicing (e.g. `.sel(lat=slice(a, b))`)
  over manual index searching.

Print a single JSON object to stdout at the end with keys:
  "value" (float), "chart_base64" (str). Do not print anything else.
Only use: xarray as xr, cf_xarray, nc_time_axis, dask, matplotlib (Agg backend), numpy, json, base64.
"""

_SUBPROCESS_PREAMBLE = """
import matplotlib
matplotlib.use("Agg")
"""


def _resolve_netcdf_path(dataset: str) -> str | None:
    """Resolves a dataset name to a local NetCDF file path.

    TODO: configure actual NetCDF file paths per dataset/scenario/region
    combination. Currently returns None (no local file configured),
    which causes the analysis agent to report a clean failure rather
    than fabricate results.

    Args:
        dataset: Dataset name resolved by the KG agent (e.g. "CMIP6").

    Returns:
        Absolute path to a NetCDF file, or None if not configured.
    """
    base_dirs = {
        "CMIP6": config.CMIP6_NETCDF_DIR,
        "CORDEX": config.CORDEX_NETCDF_DIR,
        "ERA5": config.ERA5_NETCDF_DIR,
    }
    base_dir = base_dirs.get(dataset)
    if base_dir is None:
        return None
    candidate_dir = Path(base_dir)
    if not candidate_dir.exists():
        return None
    matches = sorted(candidate_dir.glob("*.nc"))
    return str(matches[0]) if matches else None


def _probe_netcdf_metadata(netcdf_path: str) -> dict:
    """Lightweight inspection of a NetCDF file's structure so the code
    generation prompt can reference real variable/dimension names
    instead of the LLM guessing at CMOR short names.

    Args:
        netcdf_path: Path to the NetCDF file.

    Returns:
        Dict with "data_vars" (name -> {"dims", "dtype"}) and "dims"
        (dimension name -> size). Empty dict if the file can't be probed.
    """
    try:
        import xarray as xr

        with xr.open_dataset(netcdf_path) as ds:
            data_vars = {
                name: {"dims": list(var.dims), "dtype": str(var.dtype)}
                for name, var in ds.data_vars.items()
                if "bnds" not in name
            }
            dims = {k: int(v) for k, v in ds.sizes.items()}
        return {"data_vars": data_vars, "dims": dims}
    except Exception:  # noqa: BLE001 - metadata probe is best-effort
        return {}


def _run_generated_code(code: str, netcdf_path: str) -> dict:
    """Executes generated analysis code in a subprocess with a timeout.

    Args:
        code: The generated Python source code.
        netcdf_path: Path to the NetCDF file, injected as NETCDF_PATH.

    Returns:
        Dict with keys "success", and on success "value"/"chart_base64",
        or on failure "error".
    """
    full_script = (
        _SUBPROCESS_PREAMBLE
        + f"\nNETCDF_PATH = {netcdf_path!r}\n"
        + code
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp_file:
        tmp_file.write(full_script)
        tmp_path = tmp_file.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=config.ANALYSIS_TIMEOUT,
            check=False,  # returncode is checked explicitly below
            env=_minimal_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Analysis code timed out after {config.ANALYSIS_TIMEOUT}s"}
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()[-2000:]}

    try:
        output = json.loads(result.stdout.strip().splitlines()[-1])
        return {"success": True, **output}
    except (json.JSONDecodeError, IndexError):
        return {"success": False, "error": "Analysis code did not produce valid JSON output."}


# TODO: implement uncertainty quantification across ensemble runs
# (mean_value, percentile_5, percentile_95) once the base system works.
# The generated code prompt and _run_generated_code plumbing should be
# extended to loop over ensemble members and return a range, with the
# chart rendering a confidence band instead of a single line.


@traceable(name="analysis_agent")
async def run_analysis_agent(state: ClimateRiskState) -> ClimateRiskState:
    """Runs the analysis agent: only executes after a valid KG result.
    Generates and executes analysis code, or returns a clean failure —
    never a hallucinated result.

    Args:
        state: Current pipeline state. Must have kg_results with
            found=True for analysis to proceed.

    Returns:
        Updated state with analysis_results populated.
    """
    kg_results = state.kg_results or {}
    if not kg_results.get("found"):
        state.analysis_results = {
            "success": False,
            "error": "Analysis agent requires a valid KG result; none available.",
        }
        return state

    dataset = kg_results.get("dataset")
    variable = kg_results.get("variable", "unknown")
    netcdf_path = _resolve_netcdf_path(dataset) if dataset else None

    if netcdf_path is None:
        state.analysis_results = {
            "success": False,
            "error": (
                f"No local NetCDF file configured for dataset '{dataset}'. "
                "TODO: configure CMIP6_NETCDF_DIR / CORDEX_NETCDF_DIR in config.py."
            ),
            "code_used": None,
        }
        return state

    netcdf_metadata = await asyncio.to_thread(_probe_netcdf_metadata, netcdf_path)
    if not netcdf_metadata.get("data_vars"):
        state.analysis_results = {
            "success": False,
            "error": f"Could not read variable metadata from NetCDF file '{netcdf_path}'.",
            "code_used": None,
        }
        return state

    prompt = _CODE_GEN_PROMPT.format(
        query=state.user_query,
        variable=variable,
        data_vars=json.dumps(netcdf_metadata["data_vars"]),
        dims=json.dumps(netcdf_metadata["dims"]),
    )
    code, cost, llm_unavailable = await call_llm(
        model=config.ANALYSIS_AGENT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
    )
    state.litellm_cost_usd += cost
    state.llm_unavailable = state.llm_unavailable or llm_unavailable
    if llm_unavailable:
        state.analysis_results = {
            "success": False,
            "error": "LLM unavailable: could not generate analysis code.",
            "code_used": None,
        }
        return state

    code_block = code
    if "```" in code:
        parts = code.split("```")
        code_block = parts[1].removeprefix("python").strip() if len(parts) > 1 else code

    result = await asyncio.to_thread(_run_generated_code, code_block, netcdf_path)
    result["code_used"] = code_block
    state.analysis_results = result
    return state
