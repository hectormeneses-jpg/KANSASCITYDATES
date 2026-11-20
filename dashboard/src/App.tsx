import { useEffect, useRef, useState } from 'react'

// El mapa lo calcula el backend con pandas (backend/mapa_touchdown.py) y se muestra incrustado.
// Ruta relativa y sin diagonal inicial: la app se publica en una subruta.
const MAPA = 'api/mapa-touchdown'
// Cada jugada tiene su dirección: #jugada=<gameId>-<playId>. Solo se acepta ese formato.
const ID_JUGADA = /^\d+-\d+$/
const hashValido = (h: string) => (h.startsWith('#jugada=') && ID_JUGADA.test(h.slice(8)) ? h : '')

export default function App() {
  const marco = useRef<HTMLIFrameElement>(null)
  const [alto, setAlto] = useState(1400)
  const [estado, setEstado] = useState<'cargando' | 'listo' | 'error'>('cargando')
  // El hash inicial se pasa una sola vez al marco; después solo se actualiza la barra de direcciones.
  const [hashInicial] = useState(() => hashValido(window.location.hash))
  const [hash, setHash] = useState(hashInicial)

  // El mapa avisa su alto con postMessage. Así el marco crece con su contenido y no hay doble barra de desplazamiento.
  useEffect(() => {
    const alRecibir = (e: MessageEvent) => {
      if (e.source !== marco.current?.contentWindow) return
      const d = e.data as { tipo?: string; alto?: number; id?: string } | null
      if (d?.tipo === 'mapa-touchdown-alto' && typeof d.alto === 'number') {
        setAlto(Math.ceil(d.alto))
        setEstado('listo')
      }
      // El mapa avisa qué jugada se está simulando: la dirección cambia para poder compartirla.
      if (d?.tipo === 'mapa-touchdown-jugada' && typeof d.id === 'string' && ID_JUGADA.test(d.id)) {
        const nuevo = `#jugada=${d.id}`
        window.history.replaceState(null, '', nuevo)
        setHash(nuevo)
      }
    }
    window.addEventListener('message', alRecibir)
    return () => window.removeEventListener('message', alRecibir)
  }, [])

  // Si el marco cargó una respuesta de error del backend (no la página del mapa), se avisa.
  const alCargar = () => {
    const doc = marco.current?.contentDocument
    if (doc && !doc.querySelector('.pagina')) setEstado('error')
  }

  return (
    <div className="min-h-screen bg-[#0d1117] text-slate-200">
      <header className="mx-auto flex max-w-[1120px] items-center justify-between gap-4 px-4 py-3 text-sm">
        <span className="font-semibold tracking-wide">KANSASCITYDATES</span>
        <a className="text-slate-400 underline hover:text-white" href={MAPA + hash} target="_blank" rel="noreferrer">
          Abrir el mapa en una pestaña nueva
        </a>
      </header>
      {estado === 'cargando' && (
        <p className="px-4 pb-2 text-center text-sm text-slate-400" role="status">
          Calculando el mapa…
        </p>
      )}
      {estado === 'error' && (
        <p className="px-4 py-6 text-center text-sm text-amber-300" role="alert">
          No se pudo cargar el mapa. Recarga la página; si sigue igual, revisa que la carpeta data/ esté completa.
        </p>
      )}
      <iframe
        ref={marco}
        title="Mapa de probabilidad de touchdown en las últimas yardas"
        src={MAPA + hashInicial}
        onLoad={alCargar}
        scrolling="no"
        style={{ height: estado === 'error' ? 0 : alto }}
        className="block w-full border-0"
      />
    </div>
  )
}
