"""Build the coupled technical report only from complete accepted evidence.

ReportLab produces the PDF. A separate plotting interpreter renders equations
with Matplotlib after all timed splits and the data/figure reviews finish.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "coupled_report_guard", HERE / "render-study-summary.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

EQUATIONS = [
    "$\\min_x\\;\\frac{1}{2}x^T P x+q^T x+\\sum_{g}\\left(a_g M_g(A_gx)+\\frac{b_g}{2}M_g(A_gx)^2\\right)$",
    "$M_g(z)=\\max\\left(0,\\max_i c_{U,i}(z_i-u_i)_+,\\max_i c_{L,i}(\\ell_i-z_i)_+\\right)$",
    "$g_C(z)=\\inf_{s\\in C}\\Psi(z-s)=\\Psi\\left(z-\\Pi_C(z)\\right)$",
    "$\\Psi(Dw)\\leq\\Psi(w),\\qquad D=\\operatorname{diag}(d_i),\\quad 0\\leq d_i\\leq1$",
    "$\\operatorname{prox}_{g_C}^{H}(v)=\\Pi_C(v)+\\operatorname{prox}_{\\Psi}^{H}\\left(v-\\Pi_C(v)\\right)$",
    "$w_i(t)=\\operatorname{sign}(r_i)\\min\\left(|r_i|,t/c_i\\right)$",
    "$F(t)=a t+\\frac{b}{2}t^2+\\frac{1}{2}\\sum_i h_i\\left(\\max(|r_i|-t/c_i,0)\\right)^2,\\quad t\\geq0$",
    "$t=\\frac{\\sum_{i\\in S(t)}h_i|r_i|/c_i-a}{b+\\sum_{i\\in S(t)}h_i/c_i^2},\\quad S(t)=\\{i:c_i|r_i|>t\\}$",
    "$L_g(y)=\\sum_i\\left((y_i)_+/c_{U,i}+(-y_i)_+/c_{L,i}\\right)$",
    "$\\Psi_g^*(y)=\\frac{\\left(\\max(L_g(y)-a_g,0)\\right)^2}{2b_g}\\quad(b_g>0)$",
    "$g_C^*(y)=\\sigma_C(y)+\\Psi^*(y),\\qquad P x+q+A^T y=0$",
    "$P+S+A^T H A\\succ0,\\qquad S\\succ0,\\quad H\\succ0$",
    "$s^{k+1}=(1-\\alpha/2)s^k+(\\alpha/2)R_F R_G(s^k),\\quad 0<\\alpha<2$",
    "$\\bar A=D A,\\quad\\bar\\ell=D\\ell,\\quad\\bar u=D u,\\quad\\bar c=c/D$",
    "$T_{j,m}=\\operatorname{median}_{r=1,2,3}T_{j,m,r},\\qquad R_j=1-T_{j,\\mathrm{native}}/\\min_{m\\ne\\mathrm{native}}T_{j,m}$",
    "$T_{k+1}=a T_k+b Q_k+(1-a)T_{outside,k}$",
    "$\\ell_i\\leq A_i x\\leq u_i\\qquad(i\\in\\mathcal{H})$",
    "$y=D\\bar y,\\qquad H_{\\mathrm{physical}}=D\\bar H D$",
    "$u^{k+1}=\\operatorname{prox}_F^{M}(v^k-d^k)$",
    "$h^{k+1}=\\alpha u^{k+1}+(1-\\alpha)v^k$",
    "$v^{k+1}=\\operatorname{prox}_G^{M}(h^{k+1}+d^k)$",
    "$d^{k+1}=d^k+h^{k+1}-v^{k+1}$",
]

MATH_WORKER = r"""
import json,sys
from pathlib import Path
from matplotlib.mathtext import math_to_image
from matplotlib.font_manager import FontProperties
items=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
out=Path(sys.argv[2]);out.mkdir(exist_ok=True)
for i,formula in enumerate(items):
    math_to_image(formula,str(out/f'eq-{i:02}.png'),prop=FontProperties(size=13),dpi=300,format='png',color='black')
"""

REFERENCES = [
    (
        "Schwan, Lew and Plancher (2026). Efficient ADMM for Soft-Constrained Quadratic Programs via Generalized Slack Projections.",
        "https://arxiv.org/abs/2610.35631",
    ),
    (
        "Boyd et al. (2011). Distributed Optimization and Statistical Learning via the Alternating Direction Method of Multipliers.",
        "https://web.stanford.edu/~boyd/papers/admm_distr_stats.html",
    ),
    (
        "Parikh and Boyd (2014). Proximal Algorithms.",
        "https://web.stanford.edu/~boyd/papers/prox_algs.html",
    ),
    (
        "Chancelier and de Lara (2022 revision). Orthant-Strictly Monotonic Norms, Generalized Top-k and k-Support Norms and the L0 Pseudonorm.",
        "https://arxiv.org/abs/2001.10441v3",
    ),
    (
        "Perez et al. (2022). Efficient projection algorithms onto the weighted l1 ball.",
        "https://doi.org/10.1016/j.artint.2022.103683",
    ),
    (
        "DAQP. Official proximal parameters and exit flags.",
        "https://darnstrom.github.io/daqp/parameters/",
    ),
    (
        "OSQP. Model predictive control formulation.",
        "https://osqp.org/docs/examples/mpc.html",
    ),
    (
        "Santibáñez-Leal (2026). Side-Specific Soft Constraints in Quadratic Programming. Technical report 0.01.000, not peer reviewed.",
        "https://doi.org/10.5281/zenodo.23851660",
    ),
]


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(args):
    for key in ("doi", "evidence_doi"):
        value = getattr(args, key, None)
        if value is not None and not re.fullmatch(r"10\.5281/zenodo\.[1-9][0-9]*", value):
            raise ValueError("Invalid reserved publication DOI")
    if getattr(args, "doi", None) and args.doi == getattr(args, "evidence_doi", None):
        raise ValueError("Manuscript and dataset require distinct reserved DOIs")
    documents, registration, review = guard.load_complete(
        args.studies, args.review, args.registration
    )
    sums = guard.read(args.summary / "SHA256SUMS.json")
    expected_figures = {
        "summary.json",
        "observation-states.png",
        "observation-states.svg",
        "primary-full-population.png",
        "primary-full-population.svg",
    }
    if set(sums) != expected_figures:
        raise ValueError("Incomplete or unexpected reviewed figure inventory")
    figure_review = guard.read(args.figure_review)
    facts = guard.read(args.summary / "summary.json")
    if (
        figure_review["decision"] != "ACCEPT_FIGURES"
        or figure_review["evidence_review_sha256"] != guard.digest(review)
        or figure_review["renderer_sha256"]
        != file_hash(HERE / "render-study-summary.py")
        or figure_review["summary_sha256"] != sums["summary.json"]
        or figure_review["figure_sha256"]
        != {key: value for key, value in sums.items() if key != "summary.json"}
        or facts["protocol_sha256"] != registration["protocol_sha256"]
        or facts["evidence_review_sha256"] != guard.digest(review)
        or facts["source_commit"]
        != documents["heldout"]["environment"]["registration"]["commit"]
        or facts["primary"] != documents["heldout"]["primary"]
        or facts["counts"] != {key: value["counts"] for key, value in documents.items()}
    ):
        raise ValueError("Figure/facts review does not accept this complete evidence")
    for name, expected in sums.items():
        if Path(name).name != name or file_hash(args.summary / name) != expected:
            raise ValueError("Reviewed figure artifact differs")
    checksum = args.archive.with_name(args.archive.name + ".sha256")
    archive_digest = file_hash(args.archive)
    if checksum.read_text(encoding="utf-8").split()[0] != archive_digest:
        raise ValueError("Evidence ZIP differs from its verified checksum")
    archive_review = guard.read(args.archive_review)
    if (
        archive_review["decision"] != "ACCEPT_ARCHIVE"
        or archive_review["archive_sha256"] != archive_digest
        or archive_review["protocol_sha256"] != registration["protocol_sha256"]
        or archive_review["evidence_review_sha256"] != guard.digest(review)
        or archive_review["figure_review_sha256"] != guard.digest(figure_review)
    ):
        raise ValueError("Independent review does not accept this exact evidence ZIP")
    receipt_path = args.output.with_suffix(".build.json")
    if args.output.exists() or receipt_path.exists():
        raise FileExistsError("Report output and build receipt must both be new")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    math_dir = args.work
    if math_dir.exists():
        raise FileExistsError("Report equation directory must be new")
    math_dir.mkdir(parents=True)
    formulas = math_dir / "equations.json"
    formulas.write_text(json.dumps(EQUATIONS) + "\n", encoding="utf-8", newline="\n")
    subprocess.run(
        [str(args.plot_python), "-c", MATH_WORKER, str(formulas), str(math_dir)],
        check=True,
        timeout=90,
    )

    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Image,
        PageBreak,
    )

    fonts = Path(reportlab.__file__).parent / "fonts"
    for font, name in [
        ("Vera.ttf", "Body"),
        ("VeraBd.ttf", "BodyBold"),
        ("VeraIt.ttf", "BodyItalic"),
        ("VeraBI.ttf", "BodyBoldItalic"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(fonts / font)))
    pdfmetrics.registerFontFamily(
        "Body",
        normal="Body",
        bold="BodyBold",
        italic="BodyItalic",
        boldItalic="BodyBoldItalic",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Text", fontName="Body", fontSize=9.6, leading=14, spaceAfter=8
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallText", fontName="Body", fontSize=8, leading=11, spaceAfter=6
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            fontName="BodyBold",
            fontSize=22,
            leading=28,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            fontName="BodyBold",
            fontSize=15,
            leading=20,
            spaceAfter=12,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubTitle",
            fontName="BodyBold",
            fontSize=10.5,
            leading=15,
            spaceBefore=7,
            spaceAfter=7,
            keepWithNext=True,
        )
    )
    styles.add(ParagraphStyle(name="Cell", fontName="Body", fontSize=8, leading=11))
    story = []

    def p(text):
        story.append(Paragraph(text, styles["Text"]))

    def small(text):
        story.append(Paragraph(text, styles["SmallText"]))

    def heading(text, new=True):
        if new:
            story.append(PageBreak())
        story.append(Paragraph(text, styles["SectionTitle"]))

    def sub(text):
        story.append(Paragraph(text, styles["SubTitle"]))

    equation_number = 0

    def equation(index):
        nonlocal equation_number
        equation_number += 1
        image = Image(str(math_dir / f"eq-{index:02}.png"))
        width = min(image.imageWidth * 72 / 300, 450)
        image.drawWidth = width
        image.drawHeight = width * image.imageHeight / image.imageWidth
        story.extend(
            [
                Spacer(1, 4),
                Table(
                    [[image, Paragraph(f"({equation_number})", styles["SmallText"])]],
                    colWidths=[460, 30],
                    style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")],
                ),
                Spacer(1, 7),
            ]
        )

    def table(rows, widths):
        cells = [
            [Paragraph(escape(str(cell)), styles["Cell"]) for cell in row]
            for row in rows
        ]
        t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf4")),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#314c6c")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 9))

    def figure(name, caption):
        image = Image(str(args.summary / name))
        intrinsic_width, intrinsic_height = image.imageWidth, image.imageHeight
        image.drawWidth = 490
        image.drawHeight = 490 * intrinsic_height / intrinsic_width
        story.extend(
            [image, Spacer(1, 7), Paragraph(caption, styles["SmallText"]), Spacer(1, 8)]
        )

    primary = documents["heldout"]["primary"]
    estimate = 100 * primary["estimate"]
    lower, upper = [100 * x for x in primary["confidence_interval"]]
    verdict = "ESTABLISHED" if primary["established"] else "NOT ESTABLISHED"
    protocol = guard.read(args.studies / "coupled-heldout-v1/protocol.json")
    source_commit = documents["heldout"]["environment"]["registration"]["commit"]

    story.append(
        Paragraph(
            "Directional coupled peak penalties with original interval rows",
            styles["ReportTitle"],
        )
    )
    p("<b>An implementation and prospectively registered evaluation</b>")
    p(
        'Felipe Santibáñez-Leal<br/>ORCID: <a href="https://orcid.org/0000-0002-0150-3246">0000-0002-0150-3246</a>'
    )
    small("Technical report 0.02.000 | 2 November 2026 | CC BY 4.0 | Not peer reviewed")
    if getattr(args, "doi", None):
        small(f'Report DOI: <a href="https://doi.org/{args.doi}">{args.doi}</a>')
    sub("Abstract")
    p(
        "Directional group peaks price the largest weighted departure across selected interval rows. This report documents a native original-row projection implementation, its fixed-metric mathematical scope, exact comparison formulations and a prospective repeated-forecast study. The model is already expressible through directional row splitting and compact epigraphs; directional expressibility, weighted threshold operations and relaxed ADMM have prior art. The computational question is the cost of preserving the original interval-row system over a complete repeated operation."
    )
    p(
        f"The frozen primary population contains all 144 instances in six seed clusters, with 32 forecasts per observation and three measured repetitions. The registered median paired reduction score is {estimate:.3f}% with 95% seed-cluster interval [{lower:.3f}%, {upper:.3f}%]. There are {primary['failed_pairs']} failed primary pairs. The registered criterion is <b>{verdict}</b>. Failure scores remain in the population. Development and robustness are reported separately; the earlier 0.01.000 result remains a distinct immutable study."
    )
    table(
        [
            ["Primary quantity", "Frozen outcome"],
            ["Instances / seed clusters", "144 / 6"],
            ["Median paired reduction", f"{estimate:.6f}%"],
            ["95% seed-cluster interval", f"[{lower:.6f}%, {upper:.6f}%]"],
            ["Failed pairs", f"{primary['failed_pairs']} / 144"],
            ["Registered criterion", verdict],
        ],
        [245, 245],
    )
    small(
        "Scope: synthetic numerical problems and thermal forecasts on the recorded nonreserved host. The empirical criterion, mathematical scope, engineering validation and companion-app release are separate records."
    )

    heading("1. Formulation and comparison boundary")
    p(
        "Let P be symmetric positive semidefinite, q a finite vector and A a sparse constraint matrix. Interval rows have lower and upper bounds, with either side possibly absent. Disjoint groups identify soft rows; every ungrouped row remains hard. Each group has strictly positive directional scales cL and cU and nonnegative coefficients a and b."
    )
    equation(0)
    equation(16)
    p("The hard-row index set contains exactly the ungrouped rows.")
    equation(1)
    p(
        "A peak is shared across the group. Raising one row's departure can therefore change the correction allocated to another row. A group with a=b=0 has zero cost and is free; it is not converted into a hard constraint. Empty or overlapping groups, invalid intervals and negative curvature are rejected by the public API."
    )
    sub("Prior art and the claim being tested")
    p(
        "Schwan, Lew and Plancher [1] develop generalized slack projections for soft-constrained QPs. Orthant monotonicity [4], proximal maps [3] and weighted threshold/projection algorithms [5] are established concepts. Fixed relaxation uses standard splitting machinery [2]. This work provides an inspectable native implementation for directional linear-quadratic group peaks and evaluates it against exact existing formulations. No historical priority or universal runtime claim follows from the representation."
    )
    p(
        "Directional row splitting produces upper inequalities cU A x &lt;= cU u and lower inequalities -cL A x &lt;= -cL l, each with no lower bound. Their symmetric maximum equals the original directional peak. A compact epigraph instead introduces one nonnegative peak variable per active group. Both are equivalent objectives; the comparison must retain these compact alternatives."
    )

    heading("2. Box slack elimination and the metric proximal map")
    p(
        "Write C for a nonempty closed box and Psi for a proper closed convex nonnegative residual penalty with Psi(0)=0. Assume Psi decreases under every coordinatewise diagonal contraction. This permits unequal directional prices and is less restrictive than requiring sign symmetry."
    )
    equation(3)
    equation(2)
    sub("Box reduction: sufficient and necessary condition")
    p(
        "For any feasible correction s in C, the nearest-box residual r=z-PiC(z) is a diagonal contraction of z-s. Above an upper side both residuals are nonnegative and the nearest-box one is smaller; below a lower side both are nonpositive with the same magnitude ordering; an inside coordinate has zero nearest residual. Contraction monotonicity gives Psi(r) &lt;= Psi(z-s). Choosing s=PiC(z) attains equality and proves the reduction."
    )
    p(
        "Conversely, require the reduction for every box. Given w and a diagonal contraction D, choose coordinate endpoints -Dw and -w and evaluate at zero. The nearest-box residual is Dw, while -w is a feasible correction. The identity then gives Psi(Dw) &lt;= Psi(w). Thus the contraction property is also necessary for this all-box identity. Corrective slack has the opposite sign from violation residual; its cost is Phi(xi)=Psi(-xi)."
    )
    sub("Positive diagonal metric")
    p(
        "Use a strictly positive diagonal metric H. Clipping any trial point to the coordinate segment between PiC(v) and v reduces its metric distance from v. Its box residual is a diagonal contraction of the earlier residual, so its penalty also decreases. On that segment the translated objective is the proximal objective of Psi at r=v-PiC(v). The residual proximal minimizer itself lies in the same segment by the same clipping argument."
    )
    equation(4)
    p(
        "This is an exact convex-analytic identity. It supplies a projection rule and does not supply a finite-precision error bound, convergence rate or performance improvement."
    )

    heading("3. Directional peak threshold and dual checks")
    p(
        "On the residual segment, c_i is cU for a nonnegative residual and cL for a negative residual. For any shared nonnegative peak t, the best coordinate is the metric projection onto its scaled interval. The remaining problem is a scalar convex minimization."
    )
    equation(5)
    equation(6)
    p(
        "Let h_i be the diagonal metric entries. Sorting c_i |r_i| gives an active prefix. In an interval with active set S(t), the derivative vanishes at the following candidate; the consistent interval and the nonnegative endpoint determine the minimizer."
    )
    equation(7)
    p(
        "If the right derivative at zero is nonnegative, t=0. If a=b=0, return the unchanged residual directly. The kernel uses finite local floating-point spacing at threshold boundaries and rejects nonrepresentable arithmetic. An absolute tolerance floor is not a unit-invariance proof."
    )
    sub("Joint dual budget and local Fenchel checks")
    equation(8)
    equation(9)
    p(
        "For b=0, the conjugate is the indicator of L(y)&lt;=a. It is a joint group budget, not independent row caps. The box support is also needed: positive multipliers require a finite upper side, and negative multipliers require a finite lower side."
    )
    equation(10)
    p(
        "The accuracy gate checks stationarity before and after the explicitly bounded dual repair, each group's normalized absolute Fenchel gap and each hard row's complementarity separately. A negative approximate hard-row gap cannot cancel a wrong soft subgradient. Aggregate signed gap remains diagnostic. A repaired multiplier is not relabeled as exact domain membership for the original multiplier."
    )

    heading("4. Native splitting and bounded mathematical scope")
    p(
        "Consensus separates the quadratic/linear-graph block from the interval penalty block. Positive S and H make the graph proximal subproblem strongly convex. Under a finite saddle-point assumption, fixed-metric whitening gives the standard two-block splitting setting [2,3]."
    )
    p(
        "In consensus variables u=(x,z) and v, set F(x,z)=0.5 x^T P x+q^T x plus the indicator of z=A x, and let G(v) contain the hard intervals and soft interval costs. The block metric is M=diag(S,H). Write prox_F and prox_G in that fixed metric and R_F=2 prox_F-I, R_G=2 prox_G-I. After a complete step, v=prox_G(s) for s=v+d, with scaled dual d. Substituting the relaxed u/v/d updates gives the displayed reflected-map identity."
    )
    equation(11)
    equation(18)
    equation(19)
    equation(20)
    equation(21)
    equation(12)
    p(
        "After one complete step, the reflected-proximal composition is nonexpansive and its strict interior relaxation is averaged. The fixed-point/shadow argument supplies the usual convergence conclusion under the stated saddle assumption. Endpoints zero and two are excluded. Penalty coefficients do not acquire an alpha factor. This is an established relaxation argument, not a new rate theorem."
    )
    p(
        "The native public path fixes finite scalar alpha in (0,2), defaults to 1.6, uses direct linear solves and rejects adaptive rho, automatic OSQP scaling, polishing, directional sensitivities and directional code generation. Alpha is immutable within a directional workspace. These restrictions are narrower than the theoretical positive-diagonal-metric identity."
    )
    equation(13)
    equation(17)
    p(
        "Setup-time normalization uses D_i=max(cL_i,cU_i) on soft rows and D_i=1 on hard rows. D remains fixed over vector updates. It selects the corresponding physical metric, rather than preserving the old unscaled-rho trajectory. P, A, group membership, penalty coefficients/directional scales, finite-side pattern and hard-row rho classification remain fixed in a workspace. The linear objective vector q and bounds may change according to the registered forecasts."
    )
    sub("Failure and recession scope")
    p(
        "Nonfinite arithmetic and numeric failures clear purported solutions and diagnostics. A quadratic group blocks any finite-side violating recession direction. The unboundedness path conservatively requires exactly zero computed P d; ambiguous numerical directions remain unresolved. Iteration limits are failures under the study policy. Larger ambiguous coupled PSD blocks beyond the declared certification budget are unsupported rather than silently regularized."
    )

    heading("5. Registered comparators and operation boundary")
    table(
        [["Registered profile", "Backend", "Frozen controls"]]
        + [
            [name, config["backend"], json.dumps(config["settings"], sort_keys=True)]
            for name, config in protocol["methods"].items()
        ],
        [115, 125, 250],
    )
    p(
        "All candidate controls are frozen before heldout generation. Direct non-proximal DAQP requires a positive-definite augmented epigraph Hessian. Row-split GSP supports the pinned native linear infinity penalty, so squared peaks are declared incompatible. Proximal DAQP uses the unchanged PSD/LP objective. In pinned DAQP 0.10.3, one-shot LP and persistent zero-Hessian Model policies remain distinct; setup/reuse flags retain their actual meaning. DAQP status 4 or 5 is only a candidate for external checks [6]."
    )
    p(
        "One timed observation includes owned validation, construction/factorization, all 32 updates and solves, physical recovery and independent checks. Canonical generation, process/library startup and evidence serialization are excluded symmetrically. Every competing compiled library is preloaded before the inner timer. Each observation has a fresh supervised process; the workspace is reused only within that observation."
    )
    p(
        "One warmup and three measured observations are retained per method/instance. Worker wall limits include startup and serialization. The registered 30-second trial and four-hour split limits and sampled 4-GiB current/high-water RSS bound are supervision policies, not CPU or memory reservation. Unrelated host work is preserved."
    )

    heading("6. Synthetic models, inventory and accuracy")
    table(
        [
            ["Split", "Instances", "Purpose"],
            ["Development", "48", "Two registered seeds; engineering evidence"],
            ["Heldout", "144", "Six seeds, full primary population"],
            ["Robustness", "18", "Separate descriptive stress inventory"],
        ],
        [110, 70, 310],
    )
    p(
        "Each primary seed has 16 sparse cells and eight thermal cells. Sparse cases use n=32 or 96, group size 8, geometric diagonal spans 1 or 1000 before PSD zeroing, positive-definite/semidefinite base curvature and b=0 or 1. Hard coordinate bounds keep the objectives bounded. For a semidefinite Hessian its full matrix condition is infinite; the span label refers to the pre-zeroing geometric diagonal; the remaining nonzero range can be smaller."
    )
    p(
        "Thermal cases have two independent zones and horizons 12 or 24, uncondensed temperatures and heater-energy inputs. Hard initial conditions, dynamics and heater limits remain explicit; one directional comfort peak is shared over each zone's horizon. Retention, gains, outside conditions and prices are authored synthetic values. Temperature is degrees Celsius, heater input kWh per one-hour interval and objective synthetic currency. These are repeated forecasts, not measured buildings or independently evolving closed-loop policies. The conventional horizon organization follows [7]."
    )
    equation(15)
    p(
        "Robustness separately includes zero-Hessian base cases and a 1e8 diagonal span. A zero base Hessian with b&gt;0 still has a quadratic epigraph objective and is not called a pure LP."
    )
    p(
        "Candidate frames require hard-row error at most 1e-6 in declared physical units, raw and repaired normalized stationarity at most 1e-6, maximum local absolute normalized Fenchel gap at most 1e-6, joint dual-budget error at most 1e-6, normalized dual repair at most 1e-7 and normalized common-oracle objective gap at most 1e-6. Every frame must pass. The common stock-OSQP compact epigraph oracle uses absolute/relative tolerance 1e-10, 200000 iterations and a 1e-7 external gate."
    )

    p(
        "Normalized stationarity is the infinity norm of P x+q+A^T y divided by max(1, norm(P x), norm(q), norm(A^T y)), using infinity norms and taking the worse raw/repaired multiplier value. Objective discrepancy uses max(1,abs(common oracle objective)). A group's Fenchel gap denominator is max(1,abs(group cost),abs(box support),abs(y^T A x)); each hard-row denominator is max(1,abs(y_i bound_i),abs(y_i(Ax)_i)). The dual repair denominator is max(1,norm(y)); the linear dual-budget excess denominator is max(1,L,a). Nonfinite products or metrics reject before normalization."
    )

    heading("7. Primary inference and complete outcome")
    equation(14)
    p(
        "For every registered instance, take the median complete-batch elapsed time over three measured repetitions. Compare native with the fastest compatible registered baseline median, with lexical tie-breaking. Any missing or unsuccessful compatible measured observation assigns the prescribed score -1 to the entire pair and prevents qualification. Failed pairs are retained; there is no successful-only denominator."
    )
    p(
        "Resample six whole seeds with replacement, pool their complete 24-instance vectors and take the median. The frozen bootstrap uses 10000 resamples and NumPy linear 2.5/97.5 percentile limits. The criterion requires a median reduction at least 10%, lower 95% bound strictly positive and zero failed pairs. The interval reflects the six registered seed clusters and the observed workload, not universal hardware performance."
    )
    figure(
        "primary-full-population.png",
        f"All 144 registered paired scores. Overall median {estimate:.6f}%; 95% interval [{lower:.6f}%, {upper:.6f}%]. Failed pairs {primary['failed_pairs']}/144 retain their prescribed -100% score, distinct from observed negative runtime reductions.",
    )
    reasons = []
    if primary["estimate"] < 0.1:
        reasons.append("the median is below the registered 10% threshold")
    if primary["confidence_interval"][0] <= 0:
        reasons.append("the lower confidence limit is not positive")
    if primary["failed_pairs"]:
        reasons.append(
            f"{primary['failed_pairs']} primary pairs contain a failed compatible observation"
        )
    p(
        "Registered outcome: <b>"
        + verdict
        + "</b>. "
        + (
            "; ".join(reasons) + "."
            if reasons
            else "All three declared numerical/statistical conditions are satisfied for this cohort."
        )
    )

    heading("8. All observations and retained failures")
    states = sorted({state for doc in documents.values() for state in doc["counts"]})
    table(
        [["Measured state"] + list(documents)]
        + [
            [state] + [doc["counts"].get(state, 0) for doc in documents.values()]
            for state in states
        ],
        [190, 100, 100, 100],
    )
    figure(
        "observation-states.png",
        "All measured method cells in every split. Declared incompatibilities remain visible. Warmups and oracle records are retained in the complete raw journals and are not added to the measured-state counts.",
    )
    for split, doc in documents.items():
        failed = [row for row in doc["datasets"] if row["oracle_state"] != "accepted"]
        p(
            f"{split.capitalize()}: {len(doc['inventory'])} instances; {len(failed)} unsuccessful common oracle(s). "
            + (
                "Identifiers: " + ", ".join(escape(row["id"]) for row in failed) + "."
                if failed
                else "All common oracles were accepted."
            )
        )
    p(
        "A common-oracle limit does not establish that the candidate algorithm is wrong or slower. It leaves the registered comparison unsuccessful for that pair. Such a case is not replaced with another oracle, deleted, retried or reclassified as a declared model incompatibility."
    )
    p(
        "Independent replay checked 115124 returned candidate frames in the heldout journals; all met their respective external gates. The six measured batches labeled accuracy-rejected instead contain row-split-default backend iteration limits: heldout-0014 at frame 3 and heldout-0026 at frame 22, each in all three measured repetitions. These frames reached 200000 iterations with status 7 and no returned primal or dual vector; their warmups failed identically. Five common-oracle limits and two supervised timeouts are retained separately. The timeouts occurred in native on heldout-0095, measured repetition index 1, and daqp-prox-forced on heldout-0097, measured repetition index 2. No completed solution or KKT conclusion is asserted for a killed worker. Frame and repetition indices are zero-based."
    )
    p(
        "The independent heldout frame count includes valid returned frames from rejected method batches and valid prefixes of failed oracles. The automatic consumer checks 114848 accepted-batch frames. These are different scopes and must not be added together. The five unsuccessful heldout common oracles are heldout-0030/frame0, heldout-0054/frame22, heldout-0078/frame0, heldout-0106/frame3 and heldout-0110/frame3. Their dependent measured rows total 105; with the two row-split cases and two timeout cases, nine primary pairs retain the prescribed failed score."
    )
    p(
        "The independent robustness replay checks 9245 returned candidate frames, all passing their gates, versus 8960 accepted-batch frames in the automatic consumer. Its six measured accuracy-rejected batches are native and epigraph-fixed on robustness-0003, each in all three measured repetitions. Both backends reach status 7 at frames 1, 24 and 25 with 200000 iterations and no candidate vectors; their warmups behave identically. Six common-oracle limits produce 144 dependent measured oracle-failed rows. Development replay checks 39021 returned candidate frames, all passing, versus 39008 accepted-batch frames; its one failed oracle is development-0014/frame13. No failed batch or oracle is retried or removed, and robustness cannot replace the primary endpoint."
    )

    heading("9. Provenance, interpretation and availability")
    environment = documents["heldout"]["environment"]
    table(
        [
            ["Recorded item", "Value"],
            [
                "Python / platform",
                str(environment["python"]) + " / " + str(environment["platform"]),
            ],
            ["Hardware", json.dumps(environment["hardware"], sort_keys=True)],
            ["Public SDK", "softqp==0.2.0; CPython 3.12 CPU builtin"],
            ["App source commit", source_commit],
            ["Canonical protocol SHA256", registration["protocol_sha256"]],
            ["Accepted evidence review SHA256", guard.digest(review)],
            ["Verified evidence ZIP SHA256", archive_digest],
        ],
        [145, 345],
    )
    p(
        "All splits share the registered source identity, dependency map and public native/Python wheel manifests. Batch/request/observation boundaries retain original units and sparse matrix structure. The consumer checks full identity inventories, checksums, CSV correspondence and every accepted original-space frame. A separate reviewer recomputes original objective and raw/repaired KKT quantities without calling the candidate's acceptance or evaluation function."
    )
    p(
        "The related report 0.01.000 [8] records a different, immutable 456-instance separable study: median reduction 0.499839% with 95% interval [-3.291967%,3.944835%], which did not establish its 10% criterion. These cohorts, endpoints and mathematical families are not pooled into a before/after improvement claim."
    )
    p(
        "Interpretation remains limited to synthetic problems, the declared complete-operation boundary, nine registered profiles and one nonreserved host. Three repetitions and six primary clusters do not establish performance on arbitrary applications. Direct factorization costs and allocations are not isolated causal effects. Numerical equivalence and smaller principal dimensions are distinct from observed elapsed-time advantage. Prior expressibility, threshold projections and relaxed splitting remain prior art."
    )
    p(
        "The public SDK is an engineering distribution. The present technical report and evidence acceptance do not by themselves certify operational safety, field energy savings, global algorithmic priority, deployment or qualified companion-app release. AI assistance was used for implementation and document preparation; a separate AI reviewer performed adversarial validation. The named author retains responsibility for the report. This is not a peer-reviewed publication."
    )
    p(
        'Complete canonical inputs, full oracle/method journals including failures and warmups, exact CSV, registered source snapshots and checksums accompany this report in the verified evidence ZIP. The public source record is <a href="https://github.com/fsantibanezleal/CAOS_SoftQP/tree/'
        + source_commit
        + '">CAOS_SoftQP at the recorded commit</a>; the independent engine distribution is <a href="https://pypi.org/project/softqp/0.2.0/">softqp 0.2.0 on PyPI</a>. No external operational dataset or private records are required to reproduce the authored cases.'
    )
    if getattr(args, "evidence_doi", None):
        p(f'Evidence dataset DOI: <a href="https://doi.org/{args.evidence_doi}">{args.evidence_doi}</a>. Source files retain the separate license included in the archive.')
    sub("References")
    for i, (title, url) in enumerate(REFERENCES, 1):
        small(f'[{i}] {escape(title)} <a href="{url}">{escape(url)}</a>')

    def page(canvas, document):
        canvas.saveState()
        canvas.setFont("Body", 7.5)
        canvas.setFillColor(colors.HexColor("#526274"))
        canvas.drawString(
            48, 25, "SoftQP | Directional coupled study | Technical report 0.02.000"
        )
        canvas.drawRightString(A4[0] - 48, 25, str(document.page))
        canvas.restoreState()

    with args.output.open("xb") as pdf_stream:
        document = SimpleDocTemplate(
            pdf_stream,
            pagesize=A4,
            leftMargin=48,
            rightMargin=48,
            topMargin=44,
            bottomMargin=44,
            title="Directional coupled peak penalties with original interval rows",
            author="Felipe Santibáñez-Leal",
            subject="Technical report 0.02.000; complete prospectively registered evaluation; not peer reviewed",
        )
        document.build(story, onFirstPage=page, onLaterPages=page)
    receipt = {
        "state": "built-awaiting-visual-and-independent-review",
        "pdf": str(args.output.resolve()),
        "sha256": file_hash(args.output),
        "bytes": args.output.stat().st_size,
        "source_sha256": file_hash(Path(__file__)),
        "protocol_sha256": registration["protocol_sha256"],
        "evidence_review_sha256": guard.digest(review),
        "archive_sha256": archive_digest,
        "doi": getattr(args, "doi", None),
        "evidence_doi": getattr(args, "evidence_doi", None),
        "primary": primary,
    }
    with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi")
    parser.add_argument("--evidence-doi")
    for name in (
        "studies",
        "review",
        "registration",
        "summary",
        "figure-review",
        "archive",
        "archive-review",
        "plot-python",
        "output",
        "work",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f"Coupled report refused: {error}", file=sys.stderr)
        raise SystemExit(2)
