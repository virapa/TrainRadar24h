import type { Filters } from '../lib/filters'
import type { Category } from '../lib/format'
import { CATEGORY_COLOR, CATEGORY_NAME } from '../lib/format'
import type { Prefs } from '../lib/prefs'

interface Props {
  filters: Filters
  prefs: Prefs
  counts: Record<Category, number>
  onFilters(next: Filters): void
  onPrefs(next: Prefs): void
  onClose(): void
}

const CATEGORIES: Category[] = ['ave', 'ld', 'md', 'cer']

export function FiltersPanel({ filters, prefs, counts, onFilters, onPrefs, onClose }: Props) {
  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">Filtros y mapa</strong>
      </div>
      <div className="panel-body">
        <h3>Trenes</h3>
        {CATEGORIES.map((cat) => (
          <label key={cat} className="row">
            <span><i className="swatch" style={{ background: CATEGORY_COLOR[cat] }} /> {CATEGORY_NAME[cat]} <small className="muted">({counts[cat]})</small></span>
            <input type="checkbox" checked={filters[cat]} onChange={(e) => onFilters({ ...filters, [cat]: e.target.checked })} />
          </label>
        ))}
        <label className="row">
          <span>Solo con retraso de 5 min o más</span>
          <input type="checkbox" checked={filters.soloRetraso} onChange={(e) => onFilters({ ...filters, soloRetraso: e.target.checked })} />
        </label>
        <h3>Mapa</h3>
        <label className="row">
          <span>Tema claro</span>
          <input type="checkbox" checked={prefs.theme === 'light'} onChange={(e) => onPrefs({ ...prefs, theme: e.target.checked ? 'light' : 'dark' })} />
        </label>
        <label className="row">
          <span>Mostrar vías (OpenRailwayMap)</span>
          <input type="checkbox" checked={prefs.rails} onChange={(e) => onPrefs({ ...prefs, rails: e.target.checked })} />
        </label>
        <p className="muted small">Datos: Renfe (CC BY 4.0). Mapa: © OpenStreetMap, © OpenRailwayMap.</p>
      </div>
    </section>
  )
}
