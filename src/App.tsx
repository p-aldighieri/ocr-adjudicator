import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { StoreProvider, useStore } from './store'
import { Overview } from './screens/Overview'
import { Adjudicate } from './screens/Adjudicate'
import { Settings } from './screens/Settings'

function Splash({ msg }: { msg: string }) {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      <div className="animate-pulse">{msg}</div>
    </div>
  )
}

function Welcome() {
  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-slate-800 bg-slate-900/80 px-4 py-3">
        <h1 className="text-lg font-semibold text-white">OCR Adjudicator</h1>
        <p className="text-xs text-slate-400">Verify model extractions against source scans — offline.</p>
      </header>
      <div className="p-4">
        <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 p-3 text-sm text-slate-300">
          No dataset loaded yet. Import a dataset <code className="rounded bg-slate-800 px-1">.zip</code> built by
          {' '}<code className="rounded bg-slate-800 px-1">tools/build_dataset.py</code>. After the first import it works fully offline.
        </div>
        <Settings embedded />
      </div>
    </div>
  )
}

function Shell() {
  const { loading, hasDataset } = useStore()
  if (loading) return <Splash msg="loading…" />
  if (!hasDataset) return <Welcome />
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />
      <Route path="/overview" element={<Overview />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/item/:id" element={<Adjudicate />} />
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <StoreProvider>
      <HashRouter>
        <div className="mx-auto flex h-[100dvh] max-w-[520px] flex-col bg-[#0b0f14]">
          <Shell />
        </div>
      </HashRouter>
    </StoreProvider>
  )
}
