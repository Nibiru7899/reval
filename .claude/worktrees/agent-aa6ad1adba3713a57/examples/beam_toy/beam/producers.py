"""Two producers for a cantilever beam: a closed-form check and a cheap surrogate."""

from reval import Context, ProducerKind, ProducerOutput, Subject, exact_result, interval_result, producer

PARAMS = [
    "params#/beam/load_N",
    "params#/beam/length_mm",
    "params#/beam/width_mm",
    "params#/beam/height_mm",
    "params#/beam/E_MPa",
]


def _beam(ctx: Context) -> tuple[float, float, float, float, float]:
    """Load, length, width, height, Young's modulus, each read through a declared dependency."""
    p = "params#/beam/"
    load, length, width, height, young = (
        float(ctx.param(p + k)) for k in ("load_N", "length_mm", "width_mm", "height_mm", "E_MPa")
    )
    return load, length, width, height, young


@producer(
    kind=ProducerKind.ANALYTIC,
    quantity=["tip_deflection", "bending_stress"],
    cost=2.0,
    depends_on=PARAMS,
)
def beam_analytic(subject: Subject, ctx: Context) -> ProducerOutput:
    """Euler-Bernoulli cantilever: delta = 4 P L^3 / (E b h^3), sigma = 6 P L / (b h^2). Exact formulas."""
    load, length, width, height, young = _beam(ctx)
    delta = 4.0 * load * length**3 / (young * width * height**3)
    sigma = 6.0 * load * length / (width * height**2)
    return ProducerOutput(
        results=(exact_result("tip_deflection", "mm", delta), exact_result("bending_stress", "MPa", sigma))
    )


@producer(
    kind=ProducerKind.ML_PREDICTION,
    quantity="tip_deflection",
    cost=0.5,
    depends_on=[*PARAMS, "surrogate", "samples[x_mm,defl_mm]"],
    predictors=["surrogate"],
)
def beam_surrogate(subject: Subject, ctx: Context) -> ProducerOutput:
    """slope * x, half-width = largest residual on the samples; in domain if x lies in the sampled range."""
    load, length, width, height, young = _beam(ctx)
    x = load * length**3 / (young * width * height**3)
    slope = float(ctx.load("surrogate")["slope"])
    samples = ctx.load("samples")
    half = float((samples["defl_mm"] - slope * samples["x_mm"]).abs().max())
    point = slope * x
    inside = bool(samples["x_mm"].min() <= x <= samples["x_mm"].max())
    return ProducerOutput(
        results=(
            interval_result(
                "tip_deflection",
                "mm",
                point,
                point - half,
                point + half,
                uncertainty_kind="conformal",
                in_domain=inside,
            ),
        )
    )
