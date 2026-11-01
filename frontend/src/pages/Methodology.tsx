import { Callout, DocPage, DocSection, Equation, Figure, Tabs } from '@fasl-work/caos-app-shell';
import methods from '../../../content/methods.json';
import { P, useT } from '../content/bi';
import { FlowFigure } from '../content/figures';

export function Methodology() {
  const t = useT();
  return <DocPage title={{ en: 'Methodology', es: 'Metodología' }} lede={t(
    'The methods differ in their mathematical representation, numerical steps and supported penalty families. This page states the actual formulas, assumptions and checking procedure for the implemented deterministic solvers, so the same word soft never hides a changed objective, an inserted regularizer or a relaxed hard constraint.',
    'Los métodos difieren en representación matemática, pasos numéricos y familias de penalización compatibles. Esta página expone las fórmulas, los supuestos y la verificación de los solvers deterministas implementados, para que la palabra blanda no oculte otro objetivo, una regularización agregada o una restricción dura relajada.',
  )} floorWaivers={[{ floor: 'method-learned', reason: {
    en: 'This solver study implements deterministic convex optimization and has no trained parameter policy. Deep FlexQP is documented as related work with a different restoration objective and unavailable reproducibility assets. Learned methods are not labeled as implemented to satisfy a topic count.',
    es: 'Este estudio implementa optimización convexa determinista y no contiene una política entrenada de parámetros. Deep FlexQP se documenta como trabajo relacionado con otro objetivo de restauración y activos de reproducción no disponibles. No se presentan métodos aprendidos como implementados para completar un número de temas.',
  } }]}><Tabs ariaLabel={t('Optimization methods', 'Métodos de optimización')} tabs={methods.map(method => ({
    id: method.id, label: t(method.title.en, method.title.es),
    content: <DocSection area="method" kind="classical" title={method.title} refs={method.refs}>
      {method.paragraphs.map((p, i) => <P key={i} en={p.en} es={p.es} />)}
      {method.equations.map((eq, i) => <Equation key={i} tex={eq.tex} caption={t(eq.caption.en, eq.caption.es)} />)}
      <Figure caption={t('The computation and independent evidence path for this method.', 'La secuencia de cómputo y evidencia independiente de este método.')}>
        <FlowFigure stages={method.stages.map(s => t(s.en, s.es))} label={t(method.title.en, method.title.es)} />
      </Figure>
      <Callout variant="honest" title={t('Scope and limits', 'Alcance y límites')}>{t(method.scope.en, method.scope.es)}</Callout>
    </DocSection>,
  }))} /></DocPage>;
}
