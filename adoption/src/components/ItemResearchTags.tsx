import type { Item } from '../types'
import {
  ADOPTION_START_YEAR, SOUTHERN_DEFINITION, adoptionRegimeAtEvent, hasLayout,
  hasSourceKind, isSouthernState,
} from '../classifications'

export function ItemResearchTags({ item }: { item: Item }) {
  const adoptionYear = ADOPTION_START_YEAR[item.state]
  const regime = adoptionRegimeAtEvent(item)
  return (
    <>
      {hasSourceKind(item, 'newspaper') && <Tag color="cyan">newspaper</Tag>}
      {(hasLayout(item, 'table') || hasLayout(item, 'mixed')) && <Tag color="emerald">table</Tag>}
      {adoptionYear && (
        <Tag
          color="violet"
          title={`Ever a statewide-adoption state. Project cutoff: ${item.stateAdoptionCutoff ?? adoptionYear}. Event status: ${regime}.`}
        >
          ever-adoption state
        </Tag>
      )}
      {regime === 'postlaw' && <Tag color="fuchsia">regime active</Tag>}
      {regime === 'prelaw' && <Tag color="amber">pre-regime date</Tag>}
      {isSouthernState(item) && <Tag color="orange" title={SOUTHERN_DEFINITION}>Project South</Tag>}
    </>
  )
}

const TAG_COLOR = {
  cyan: 'bg-cyan-500/15 text-cyan-300',
  emerald: 'bg-emerald-500/15 text-emerald-300',
  violet: 'bg-violet-500/15 text-violet-300',
  fuchsia: 'bg-fuchsia-500/15 text-fuchsia-300',
  amber: 'bg-amber-500/15 text-amber-300',
  orange: 'bg-orange-500/15 text-orange-300',
} as const

function Tag({
  children, color, title,
}: {
  children: React.ReactNode
  color: keyof typeof TAG_COLOR
  title?: string
}) {
  return <span title={title} className={`rounded px-1.5 py-0.5 text-[10px] ${TAG_COLOR[color]}`}>{children}</span>
}
