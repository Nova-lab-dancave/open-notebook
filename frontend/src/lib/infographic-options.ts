import type { InfographicAspect } from '@/lib/types/api'

/**
 * Infographic styles, layouts and aspects offered in the Generate Infographic
 * dialog. The ids must match the backend registry
 * (`open_notebook/utils/infographic.py`); `tests/test_infographics.py` checks it.
 *
 * `swatch` is a preview of the style's own palette (background, ink, accent):
 * it shows what the generated image will look like, so it is not themed.
 */
export interface InfographicStyleOption {
  id: string
  labelKey: string
  descKey: string
  swatch: [string, string, string]
}

export interface InfographicLayoutOption {
  id: string
  labelKey: string
}

export interface InfographicAspectOption {
  id: InfographicAspect
  labelKey: string
}

export const INFOGRAPHIC_STYLES: InfographicStyleOption[] = [
  { id: 'clean-editorial', labelKey: 'infographic.styleCleanEditorial', descKey: 'infographic.styleCleanEditorialDesc', swatch: ['#FAFAF7', '#1A1A1A', '#0F766E'] },
  { id: 'craft-handmade', labelKey: 'infographic.styleCraftHandmade', descKey: 'infographic.styleCraftHandmadeDesc', swatch: ['#FFF8F0', '#F4A261', '#2A9D8F'] },
  { id: 'chalkboard', labelKey: 'infographic.styleChalkboard', descKey: 'infographic.styleChalkboardDesc', swatch: ['#1C2B1C', '#F5F5F5', '#FFE566'] },
  { id: 'technical-schematic', labelKey: 'infographic.styleBlueprint', descKey: 'infographic.styleBlueprintDesc', swatch: ['#1E3A5F', '#E0F2FE', '#F59E0B'] },
  { id: 'subway-map', labelKey: 'infographic.styleSubwayMap', descKey: 'infographic.styleSubwayMapDesc', swatch: ['#F5F5F5', '#E63946', '#1D4ED8'] },
  { id: 'corporate-memphis', labelKey: 'infographic.styleFlatVector', descKey: 'infographic.styleFlatVectorDesc', swatch: ['#FFFFFF', '#6C5CE7', '#FF7675'] },
  { id: 'cyberpunk-neon', labelKey: 'infographic.styleNeon', descKey: 'infographic.styleNeonDesc', swatch: ['#0B0B1A', '#FF2BD6', '#00F0FF'] },
  { id: 'aged-academia', labelKey: 'infographic.styleVintage', descKey: 'infographic.styleVintageDesc', swatch: ['#F2E6CF', '#3E2C1C', '#9B2226'] },
  { id: 'kawaii', labelKey: 'infographic.styleKawaii', descKey: 'infographic.styleKawaiiDesc', swatch: ['#FFF7FB', '#FFC8DD', '#CDB4DB'] },
  { id: 'pixel-art', labelKey: 'infographic.stylePixelArt', descKey: 'infographic.stylePixelArtDesc', swatch: ['#1B1B3A', '#FFD60A', '#3DDC97'] },
  { id: 'ikea-manual', labelKey: 'infographic.styleManual', descKey: 'infographic.styleManualDesc', swatch: ['#FFFFFF', '#111111', '#0058A3'] },
  { id: 'bold-graphic', labelKey: 'infographic.styleComicPop', descKey: 'infographic.styleComicPopDesc', swatch: ['#FFD60A', '#111111', '#E63946'] },
  { id: 'morandi-journal', labelKey: 'infographic.styleJournal', descKey: 'infographic.styleJournalDesc', swatch: ['#F7F3EE', '#C9A9A6', '#A3B18A'] },
  { id: 'ui-wireframe', labelKey: 'infographic.styleWireframe', descKey: 'infographic.styleWireframeDesc', swatch: ['#F1F1F1', '#9CA3AF', '#2563EB'] },
]

export const INFOGRAPHIC_LAYOUTS: InfographicLayoutOption[] = [
  { id: 'auto', labelKey: 'infographic.layoutAuto' },
  { id: 'bento-grid', labelKey: 'infographic.layoutBento' },
  { id: 'linear-progression', labelKey: 'infographic.layoutTimeline' },
  { id: 'binary-comparison', labelKey: 'infographic.layoutVersus' },
  { id: 'comparison-matrix', labelKey: 'infographic.layoutMatrix' },
  { id: 'hierarchical-layers', labelKey: 'infographic.layoutPyramid' },
  { id: 'tree-branching', labelKey: 'infographic.layoutTree' },
  { id: 'hub-spoke', labelKey: 'infographic.layoutHub' },
  { id: 'funnel', labelKey: 'infographic.layoutFunnel' },
  { id: 'iceberg', labelKey: 'infographic.layoutIceberg' },
  { id: 'circular-flow', labelKey: 'infographic.layoutCycle' },
  { id: 'venn-diagram', labelKey: 'infographic.layoutVenn' },
  { id: 'winding-roadmap', labelKey: 'infographic.layoutRoadmap' },
  { id: 'dashboard', labelKey: 'infographic.layoutDashboard' },
]

export const INFOGRAPHIC_ASPECTS: InfographicAspectOption[] = [
  { id: 'portrait', labelKey: 'infographic.aspectPortrait' },
  { id: 'landscape', labelKey: 'infographic.aspectLandscape' },
  { id: 'square', labelKey: 'infographic.aspectSquare' },
]

export const DEFAULT_INFOGRAPHIC_STYLE = 'clean-editorial'
export const DEFAULT_INFOGRAPHIC_LAYOUT = 'auto'
export const DEFAULT_INFOGRAPHIC_ASPECT: InfographicAspect = 'portrait'
