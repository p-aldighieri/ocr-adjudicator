import { useEffect, useMemo, useState } from 'react'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import type { ImageRef, Overlay } from '../types'
import { imageURL } from '../dataset'

const SRC_COLOR: Record<string, string> = {
  claude: '#34d399', // emerald
  codex: '#fbbf24',  // amber
  current: '#60a5fa',
}

export function ImageViewer({
  images,
  overlays,
  activeImageId,
  onPickImage,
  activeField,
  showOverlays,
  showRow,
}: {
  images: ImageRef[]
  overlays: Record<string, Overlay>
  activeImageId: string | null
  onPickImage: (id: string) => void
  activeField: string | null
  showOverlays: boolean
  showRow: boolean
}) {
  const active = images.find((i) => i.id === activeImageId) ?? images[0]
  const [urls, setUrls] = useState<Record<string, string>>({})

  // resolve (and cache) object URLs for every image of this item
  useEffect(() => {
    let alive = true
    Promise.all(images.map(async (im) => [im.file, await imageURL(im.file)] as const)).then((pairs) => {
      if (!alive) return
      const m: Record<string, string> = {}
      for (const [f, u] of pairs) m[f] = u
      setUrls(m)
    })
    return () => { alive = true }
  }, [images])

  const ov = active ? overlays[active.id] : undefined
  const url = active ? urls[active.file] : undefined

  const boxes = useMemo(() => ov?.boxes ?? [], [ov])
  const cols = ov?.cols ?? []
  const activeSection = activeField
    ? activeField.startsWith('inc')
      ? 'income'
      : activeField.startsWith('enr')
        ? 'enrollment'
        : activeField.startsWith('fac')
          ? 'faculty'
          : null
    : null

  if (!active) {
    return <div className="flex h-full items-center justify-center text-slate-500">No image</div>
  }

  return (
    <div className="flex h-full flex-col">
      {/* image chips */}
      {images.length > 1 && (
        <div className="no-scrollbar flex gap-1 overflow-x-auto px-2 pb-1">
          {images.map((im) => (
            <button
              key={im.id}
              onClick={() => onPickImage(im.id)}
              className={`shrink-0 rounded px-2 py-1 text-xs ${
                im.id === active.id ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300'
              }`}
            >
              {im.role === 'snippet' ? '✂ ' : '▦ '}
              {im.side}
            </button>
          ))}
        </div>
      )}

      <div className="viewer-surface relative flex-1 overflow-hidden bg-black">
        <TransformWrapper
          key={active.id}
          minScale={0.5}
          maxScale={12}
          doubleClick={{ mode: 'zoomIn', step: 0.8 }}
          centerOnInit
          limitToBounds={false}
        >
          {({ zoomIn, zoomOut, resetTransform }) => (
            <>
              <TransformComponent
                wrapperStyle={{ width: '100%', height: '100%' }}
                contentStyle={{ width: '100%' }}
              >
                <div className="relative w-full">
                  {url ? (
                    <img src={url} alt={active.label} className="block w-full select-none" draggable={false} />
                  ) : (
                    <div className="flex h-40 items-center justify-center text-slate-600">loading…</div>
                  )}
                  {showOverlays && (
                    <svg
                      viewBox="0 0 1 1"
                      preserveAspectRatio="none"
                      className="pointer-events-none absolute inset-0 h-full w-full"
                    >
                      {showRow && cols.map((c, i) => {
                        const on = c.field === activeField || c.field === activeSection
                        return (
                          <rect
                            key={`col${i}`}
                            x={c.x}
                            y={0}
                            width={c.w}
                            height={1}
                            fill="#38bdf8"
                            fillOpacity={on ? 0.16 : 0.05}
                            stroke="#38bdf8"
                            strokeOpacity={on ? 0.8 : 0.25}
                            strokeWidth={on ? 0.003 : 0.0015}
                          />
                        )
                      })}
                      {showRow && ov?.row && (
                        <rect
                          x={0}
                          y={ov.row.y}
                          width={1}
                          height={ov.row.h}
                          fill="#facc15"
                          fillOpacity={0.12}
                          stroke="#facc15"
                          strokeOpacity={0.5}
                          strokeWidth={0.0015}
                        />
                      )}
                      {boxes.map((b, i) => {
                        const isActive = activeField && b.field === activeField
                        const color = SRC_COLOR[b.source] ?? '#a78bfa'
                        return (
                          <rect
                            key={i}
                            x={b.x}
                            y={b.y}
                            width={b.w}
                            height={b.h}
                            fill={color}
                            fillOpacity={isActive ? 0.22 : 0.08}
                            stroke={color}
                            strokeOpacity={isActive ? 1 : 0.7}
                            strokeWidth={isActive ? 0.004 : 0.0022}
                          />
                        )
                      })}
                    </svg>
                  )}
                </div>
              </TransformComponent>

              {/* zoom controls */}
              <div className="absolute bottom-2 right-2 flex flex-col gap-1">
                <ZoomBtn onClick={() => zoomIn()}>+</ZoomBtn>
                <ZoomBtn onClick={() => zoomOut()}>−</ZoomBtn>
                <ZoomBtn onClick={() => resetTransform()}>⤢</ZoomBtn>
              </div>
              <div className="absolute left-2 top-2 rounded bg-black/60 px-2 py-0.5 text-[11px] text-slate-200">
                {active.label}
              </div>
            </>
          )}
        </TransformWrapper>
      </div>
    </div>
  )
}

function ZoomBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="h-9 w-9 rounded-full bg-slate-700/90 text-lg text-white shadow active:bg-slate-600"
    >
      {children}
    </button>
  )
}
