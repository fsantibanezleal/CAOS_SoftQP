import { Callout, DocPage, DocSection, Equation, ExecutiveView, Figure, Glossary, Tabs } from '@fasl-work/caos-app-shell';
import executive from '../../../content/executive.json';
import { P, useT } from '../content/bi';
import { FlowFigure } from '../content/figures';

export function Introduction() { return <IntroductionPage data={executive} />; }
export function IntroductionPage({ data }: { data: unknown }) {
  const t = useT();
  return <DocPage title={{ en: 'Introduction', es: 'Introducción' }} lede={t(
    'Constraint conflicts are decisions about operating policy as well as numerical optimization. This workbench makes hard and soft limits, side-specific costs, solver assumptions and independent checks visible together, using reproducible control and building-energy cases whose results can be inspected and exported.',
    'Los conflictos entre restricciones son decisiones de política operativa y de optimización numérica. Este banco de trabajo reúne límites duros y blandos, costos por lado, supuestos de los métodos y verificaciones independientes mediante casos reproducibles de control y energía de edificios cuyos resultados se pueden inspeccionar y exportar.',
  )}><Tabs ariaLabel={t('Introduction views', 'Vistas de la introducción')} tabs={[
    { id: 'executive', label: t('Executive', 'Ejecutiva'), content: <ExecutiveView data={data} base={import.meta.env.BASE_URL} /> },
    { id: 'technical', label: t('Technical', 'Técnica'), content: <TechnicalView /> },
  ]} /></DocPage>;
}

function TechnicalView() {
  const t = useT();
  return <>
    <DocSection title={{ en: 'The engineering decision', es: 'La decisión de ingeniería' }} area="problem" refs={['mpc', 'gsp']}>
      <P en="A predictive controller or an energy scheduler chooses a vector of actions subject to a model and operating limits. A disturbance can make a preferred state boundary conflict with the available actuator authority. In a building, the corresponding trade-off can involve comfort, battery reserve, a contracted import limit and the cost of electricity. These consequences need a declared owner and physical units before a solver is selected."
        es="Un controlador predictivo o un programador energético elige acciones sujetas a un modelo y a límites operativos. Una perturbación puede hacer que un límite de estado deseado entre en conflicto con la capacidad del actuador. En un edificio, el compromiso puede involucrar confort, reserva de batería, un límite contratado de importación y el costo de la electricidad. Estas consecuencias requieren responsables y unidades físicas antes de elegir un solver." />
      <P en="A soft constraint permits a selected violation and assigns it an explicit cost. It does not authorize every requirement to yield. Dynamics, physical actuator limits and other hard rows keep their original feasible set, while selected state or comfort rows acquire a penalty. Returning an elastic optimum therefore answers a specified mathematical question; it does not by itself establish that the engineering policy is acceptable."
        es="Una restricción blanda permite un incumplimiento seleccionado y le asigna un costo explícito. No autoriza a flexibilizar todos los requisitos. La dinámica, los límites físicos de actuadores y otras filas duras conservan su conjunto factible, mientras ciertos límites de estado o confort reciben una penalización. Obtener un óptimo elástico responde una pregunta matemática específica; por sí solo no establece que la política de ingeniería sea aceptable." />
    </DocSection>
    <DocSection title={{ en: 'Convexity, policy and units', es: 'Convexidad, política y unidades' }} area="principles" refs={['osqp', 'gsp', 'daqp']}>
      <P en="The quadratic objective must be convex, and each supported soft penalty must be convex in its violation. Nonnegative linear and quadratic side coefficients satisfy that condition. The lower and upper sides may represent different operating consequences, so equal coefficients are a modeling choice rather than a physical law. The asymmetric method is restricted to independent row penalties; a coupled group norm is a different mathematical object."
        es="El objetivo cuadrático debe ser convexo y cada penalización admitida debe ser convexa en su incumplimiento. Los coeficientes lineales y cuadráticos no negativos cumplen esa condición. Los lados inferior y superior pueden representar consecuencias operativas distintas, de modo que igualar sus coeficientes es una decisión de modelación. El método asimétrico se restringe a penalizaciones independientes por fila; una norma que acopla un grupo es otro objeto matemático." />
      <P en="Constraint scaling changes the numerical representation without changing the intended physical decision only when bounds and penalty coefficients are transformed consistently. A temperature deviation cannot be added to a power deviation merely because both appear as floating-point values. The workbench retains a unit and hard/soft policy for every row, filters violation plots by unit, and recomputes the original-space objective independently of the solver's own cost field."
        es="Escalar restricciones cambia la representación numérica sin alterar la decisión física solo si los límites y los coeficientes se transforman de forma coherente. Una desviación de temperatura no puede sumarse a una desviación de potencia porque ambas sean números de punto flotante. El banco conserva la unidad y la política dura o blanda de cada fila, filtra los gráficos por unidad y recalcula el objetivo original de manera independiente del costo informado por el solver." />
    </DocSection>
    <DocSection title={{ en: 'The declared optimization problem', es: 'El problema de optimización declarado' }} area="math" refs={['osqp', 'gsp', 'daqp']}>
      <Equation tex={String.raw`\min_x\; f(x)=\tfrac12 x^\top P x+q^\top x,\qquad l\le Ax\le u,\quad P\succeq0`} caption={t('The hard convex QP. Infinite endpoints represent absent bound sides; the matrix P is symmetric.', 'El QP convexo duro. Los extremos infinitos representan lados ausentes; P es simétrica.')} />
      <Equation tex={String.raw`v_l=(l-Ax)_+,\quad v_u=(Ax-u)_+,\qquad \xi=v_l-v_u`} caption={t('Violation magnitudes are nonnegative. Signed slack is positive for lower undershoot and negative for upper overshoot.', 'Las magnitudes son no negativas. La holgura firmada es positiva por déficit inferior y negativa por exceso superior.')} />
      <Equation tex={String.raw`\min_x f(x)+\sum_{i\in\mathcal S}\left(a_{l,i}v_{l,i}+a_{u,i}v_{u,i}+\tfrac12 b_{l,i}v_{l,i}^2+\tfrac12 b_{u,i}v_{u,i}^2\right)`} caption={t('The separable side-specific elastic objective. Rows outside the soft set remain hard constraints.', 'El objetivo elástico separable por lado. Las filas fuera del conjunto blando permanecen como restricciones duras.')} />
      <P en="Pure quadratic, pure linear and elastic-net penalties express different preferences. A sufficiently large linear penalty may recover a feasible hard optimum under the appropriate exact-penalty conditions, while a finite quadratic penalty generally trades small violations against the base objective. Feasibility restoration is another policy and must be identified explicitly rather than compared with arbitrary elastic costs as though the objectives were identical."
        es="Las penalizaciones puramente cuadráticas, puramente lineales y mixtas expresan preferencias distintas. Una penalización lineal suficientemente grande puede recuperar un óptimo duro factible bajo las condiciones de exactitud correspondientes, mientras una cuadrática finita suele intercambiar pequeños incumplimientos por mejoras del objetivo base. La restauración de factibilidad es otra política y debe identificarse de manera explícita al comparar resultados." />
      <Glossary entries={[
        { term: 'x', definition: { en: 'decision vector in the case model', es: 'vector de decisiones del modelo' } },
        { term: 'P', definition: { en: 'symmetric positive semidefinite Hessian', es: 'hessiana simétrica semidefinida positiva' } },
        { term: 'q', definition: { en: 'linear objective coefficients', es: 'coeficientes lineales del objetivo' } },
        { term: 'A', definition: { en: 'constraint-row matrix', es: 'matriz de filas de restricción' } },
        { term: 'l, u', definition: { en: 'lower and upper interval endpoints', es: 'extremos inferior y superior del intervalo' } },
        { term: '𝒮', definition: { en: 'rows explicitly allowed to yield', es: 'filas autorizadas explícitamente a ceder' } },
        { term: 'v_l', definition: { en: 'nonnegative lower-bound violation', es: 'incumplimiento inferior no negativo' } },
        { term: 'v_u', definition: { en: 'nonnegative upper-bound violation', es: 'incumplimiento superior no negativo' } },
        { term: 'ξ', definition: { en: 'signed slack added to Ax', es: 'holgura firmada que se agrega a Ax' } },
        { term: 'a_l, a_u', definition: { en: 'linear costs per unit violation', es: 'costos lineales por unidad de incumplimiento' } },
        { term: 'b_l, b_u', definition: { en: 'quadratic costs per squared violation unit', es: 'costos cuadráticos por unidad de incumplimiento al cuadrado' } },
        { term: 'ρ', definition: { en: 'ADMM numerical penalty, distinct from an operating violation cost', es: 'penalización numérica de ADMM, distinta del costo operativo de incumplir' } },
      ]} />
    </DocSection>
    <DocSection title={{ en: 'From a model to inspectable evidence', es: 'Del modelo a evidencia inspeccionable' }} area="pipeline" noRefsReason={{ en: 'Describes the implemented product pipeline.', es: 'Describe el pipeline implementado.' }}>
      <ol>{[
        t('Declare matrices, bounds, row policy, units and penalty coefficients.', 'Declarar matrices, límites, política, unidades y coeficientes.'),
        t('Validate dimensions, finite coefficients, interval consistency and convexity assumptions.', 'Validar dimensiones, coeficientes finitos, intervalos y convexidad.'),
        t('Execute compatible native and lifted formulations with recorded numerical settings.', 'Ejecutar formulaciones nativas y explícitas compatibles con parámetros registrados.'),
        t('Recompute costs and physical violations, preserve failures and export a checksummed inventory.', 'Recalcular costos e incumplimientos, conservar fallos y exportar un inventario con hashes.'),
        t('Verify schema and digest in the browser before drawing a result or exporting its record.', 'Verificar esquema y hash en el navegador antes de dibujar o exportar un resultado.'),
      ].map(s => <li key={s}>{s}</li>)}</ol>
      <Figure caption={t('The native scientific pipeline produces an immutable record; the browser verifies and replays it.', 'El pipeline científico nativo produce un registro inmutable; el navegador lo verifica y reproduce.')}><FlowFigure stages={[t('Case specification', 'Especificación'), t('Native solvers', 'Solvers nativos'), t('Independent checks', 'Verificaciones'), t('Verified replay', 'Reproducción')]} label={t('Soft-QP evidence pipeline', 'Pipeline de evidencia de QP blandos')} /></Figure>
    </DocSection>
    <DocSection title={{ en: 'What the evidence can establish', es: 'Qué puede establecer la evidencia' }} area="honesty" refs={['gsp', 'flex']}>
      <P en="The present cases are deterministic authored models or a licensed reproduction of the paper's synthetic building model. They establish inspectable numerical behavior for the declared formulation, not field performance or operational safety. Agreement with explicit lifting and original-space residual checks is necessary correctness evidence, while repeated held-out measurements and a current prior-art review are still needed before asserting timing improvements or a new research contribution."
        es="Los casos actuales son modelos deterministas propios o una reproducción autorizada del modelo sintético de edificio del artículo. Establecen comportamiento numérico inspeccionable para la formulación declarada, no desempeño en terreno ni seguridad operativa. Coincidir con holguras explícitas y verificar residuos originales aporta evidencia necesaria de corrección, pero todavía se requieren mediciones repetidas reservadas y revisión bibliográfica para afirmar mejoras de rapidez o una contribución nueva." />
      <Callout variant="honest" title={t('Development evidence, with explicit limits', 'Evidencia de desarrollo con límites explícitos')}>{t('The browser currently replays native results. A result that exists is not automatically an accepted engineering decision. Full comparison and release gates remain in progress, and the technical report is not yet released.', 'El navegador reproduce resultados nativos. La existencia de un resultado no lo convierte en una decisión de ingeniería aceptada. La comparación completa y las verificaciones de publicación siguen en curso; el informe técnico aún no está publicado.')}</Callout>
    </DocSection>
  </>;
}
