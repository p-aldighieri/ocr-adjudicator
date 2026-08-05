import { useEffect, useState, type ReactNode } from 'react'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import type { EvidenceRef, EvidenceRole } from '../types'
import { assetURL } from '../dataset'

const ROLE_ICON: Record<EvidenceRole, string> = {
  image: '▦',
  pdf_page: '▤',
  text: '¶',
  url: '↗',
}

function isPictorial(e: EvidenceRef): boolean {
  return e.role === 'image' || e.role === 'pdf_page'
}

export function EvidencePane({
  evidence,
  activeId,
  onPick,
  relevantIds,
  wrapText,
}: {
  evidence: EvidenceRef[]
  activeId: string | null
  onPick: (id: string) => void
  /** evidence cited by the focused claim — those chips get a ring */
  relevantIds: string[]
  wrapText: boolean
}) {
  const active = evidence.find((e) => e.id === activeId) ?? evidence[0]
  const [urls, setUrls] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, boolean>>({})

  // resolve (and cache) object URLs for every pictorial evidence item of this bundle
  useEffect(() => {
    let alive = true
    const files = evidence.filter(isPictorial).map((e) => e.file).filter((f): f is string => !!f)
    Promise.all(files.map(async (f) => [f, await assetURL(f)] as const)).then((pairs) => {
      if (!alive) return
      const m: Record<string, string> = {}
      for (const [f, u] of pairs) m[f] = u
      setUrls(m)
    })
    return () => { alive = false }
  }, [evidence])

  const markFailed = (file?: string) => {
    if (file) setFailed((p) => ({ ...p, [file]: true }))
  }

  if (!active) {
    return <div className="flex h-full items-center justify-center text-slate-500">No evidence attached</div>
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* evidence chips */}
      {evidence.length > 1 && (
        <div className="no-scrollbar flex gap-1 overflow-x-auto px-2 pb-1 pt-1">
          {evidence.map((e) => {
            const on = e.id === active.id
            const cited = relevantIds.includes(e.id)
            return (
              <button
                key={e.id}
                onClick={() => onPick(e.id)}
                title={e.sourceLine}
                className={`shrink-0 rounded px-2 py-1 text-xs ${
                  on ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300'
                } ${cited && !on ? 'ring-1 ring-sky-400/60' : ''}`}
              >
                {ROLE_ICON[e.role]} {e.label}
              </button>
            )
          })}
        </div>
      )}

      <div className="min-h-0 flex-1">
        {isPictorial(active)
          ? <PictorialView
              evidence={active}
              url={active.file ? urls[active.file] : undefined}
              failed={!!(active.file && failed[active.file])}
              onError={() => markFailed(active.file)}
            />
          : active.role === 'text'
            ? <TextView evidence={active} wrapText={wrapText} />
            : <LinkView evidence={active} />}
      </div>
    </div>
  )
}

function PictorialView({
  evidence, url, failed, onError,
}: {
  evidence: EvidenceRef
  url?: string
  failed: boolean
  onError: () => void
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="viewer-surface relative min-h-0 flex-1 overflow-hidden bg-black">
        <TransformWrapper
          key={evidence.id}
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
                  {failed ? (
                    <div className="flex h-40 items-center justify-center px-4 text-center text-xs text-rose-300">
                      asset missing: <span className="ml-1 font-mono">{evidence.file}</span>
                    </div>
                  ) : url ? (
                    <img
                      src={url}
                      alt={evidence.label}
                      onError={onError}
                      className="block w-full select-none"
                      draggable={false}
                    />
                  ) : (
                    <div className="flex h-40 items-center justify-center text-slate-600">loading…</div>
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
                {evidence.label}
              </div>
            </>
          )}
        </TransformWrapper>
      </div>
      <SourceLine>{evidence.sourceLine}</SourceLine>
    </div>
  )
}

function TextView({ evidence, wrapText }: { evidence: EvidenceRef; wrapText: boolean }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto bg-slate-950/60 px-3 py-2">
        <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">{evidence.label}</div>
        <pre
          className={`font-mono text-[13px] leading-relaxed text-slate-200 ${
            wrapText ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'
          }`}
        >
          {evidence.text ?? '(no text supplied)'}
        </pre>
      </div>
      <SourceLine>{evidence.sourceLine}</SourceLine>
    </div>
  )
}

function LinkView({ evidence }: { evidence: EvidenceRef }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto px-3 py-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">{evidence.label}</div>
          {evidence.text && (
            <p className="mb-3 text-[13px] leading-snug text-slate-300">{evidence.text}</p>
          )}
          {evidence.href ? (
            <a
              href={evidence.href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block break-all rounded-lg bg-sky-600 px-3 py-2 text-sm text-white active:bg-sky-500"
            >
              Open source ↗
            </a>
          ) : (
            <span className="text-xs italic text-slate-500">no URL supplied</span>
          )}
          {evidence.href && (
            <p className="mt-2 break-all font-mono text-[11px] text-slate-600">{evidence.href}</p>
          )}
        </div>
      </div>
      <SourceLine>{evidence.sourceLine}</SourceLine>
    </div>
  )
}

function SourceLine({ children }: { children: ReactNode }) {
  return (
    <div className="shrink-0 border-t border-slate-800 bg-slate-900/70 px-3 py-1.5 text-[11px] leading-snug text-slate-400">
      {children}
    </div>
  )
}

function ZoomBtn({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="h-9 w-9 rounded-full bg-slate-700/90 text-lg text-white shadow active:bg-slate-600"
    >
      {children}
    </button>
  )
}
