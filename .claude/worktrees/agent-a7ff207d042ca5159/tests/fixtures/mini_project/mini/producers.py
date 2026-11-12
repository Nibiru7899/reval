"""Four deterministic producers; expected results are derived by hand in ../EXPECTED.md."""

from mini.helpers import is_duty_cycle, peak_load
from reval import Context, ProducerKind, ProducerOutput, Subject, exact_result, interval_result, producer
from reval.domain.evidence import Scope, Tolerance


def _is_s1(subject: Subject) -> bool:
    return subject.id == "S1"


def _is_design(subject: Subject) -> bool:
    return subject.kind.value == "design"


@producer(
    kind=ProducerKind.ML_PREDICTION,
    quantity="temp_peak",
    cost=1.0,
    depends_on=["surrogate", "params#/load/scale", "data[temp,x]"],
    assumes=["A-ambient"],
    predictors=["surrogate"],
    available_for=is_duty_cycle,
)
def predict_temp(subject: Subject, ctx: Context) -> ProducerOutput:
    """slope * scale * max(load) + intercept, with a conformal-style half-width = max |residual| on `data`."""
    model = ctx.load("surrogate")
    scale = float(ctx.param("params#/load/scale"))
    data = ctx.load("data")
    resid = (data["temp"] - (model["slope"] * data["x"] + model["intercept"])).abs().max()
    half = float(resid)
    point = model["intercept"] + model["slope"] * scale * peak_load(subject)
    lo_amb, hi_amb = ctx.assumption("A-ambient").bounds or (0.0, 0.0)
    return ProducerOutput(
        results=(
            interval_result(
                "temp_peak",
                "degC",
                point,
                point - half,
                point + half,
                uncertainty_kind="conformal",
                in_domain=_is_s1(subject),
            ),
        ),
        scope=Scope(box={"ambient": (lo_amb, hi_amb)}, assumption_ids=("A-ambient",)),
    )


@producer(
    kind=ProducerKind.PHYSICS_SIM,
    quantity="temp_peak",
    cost=3.0,
    depends_on=["params#/load/scale", "params#/sim/gain"],
    assumes=["A-sim-sens"],
    predictors=["params"],
    available_for=is_duty_cycle,
)
def sim_temp(subject: Subject, ctx: Context) -> ProducerOutput:
    """20 + 10 * gain * scale * max(load), model-form band 2 K."""
    scale = float(ctx.param("params#/load/scale"))
    gain = float(ctx.param("params#/sim/gain"))
    peak = peak_load(subject)
    point = 20.0 + 10.0 * gain * scale * peak
    return ProducerOutput(
        results=(
            interval_result(
                "temp_peak", "degC", point, point - 2.0, point + 2.0, uncertainty_kind="model_form"
            ),
        ),
        scope=Scope(assumption_ids=("A-sim-sens",)),
        tolerances=(
            Tolerance(
                selector="params#/load/scale",
                sensitivity=10.0 * gain * peak,
                input_unit="dimensionless",
                output_unit="K",
                valid_range=(0.5, 1.5),
                source="analytic derivative of the simulator formula",
                assumption_id="A-sim-sens",
            ),
        ),
    )


@producer(
    kind=ProducerKind.MEASUREMENT,
    quantity="temp_peak",
    cost=10.0,
    depends_on=["data[temp]"],
    available_for=_is_s1,
)
def measure_temp(subject: Subject, ctx: Context) -> ProducerOutput:
    """Peak recorded temperature +- 0.5 K sensor uncertainty."""
    peak = float(ctx.load("data")["temp"].max())
    return ProducerOutput(
        results=(
            interval_result("temp_peak", "degC", peak, peak - 0.5, peak + 0.5, uncertainty_kind="sensor"),
        )
    )


@producer(
    kind=ProducerKind.ANALYTIC,
    quantity="shaft_d",
    cost=0.5,
    depends_on=["params#/shaft/d_mm"],
    available_for=_is_design,
)
def shaft_check(subject: Subject, ctx: Context) -> ProducerOutput:
    """Nominal shaft diameter from the parameters, as an exact value."""
    return ProducerOutput(results=(exact_result("shaft_d", "mm", float(ctx.param("params#/shaft/d_mm"))),))
