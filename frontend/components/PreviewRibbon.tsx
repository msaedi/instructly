export default function PreviewRibbon() {
  return (
    <div style={{
      position: 'fixed', top: 12, right: -36, transform: 'rotate(45deg)',
      background: 'rgba(0,0,0,0.8)', color: '#fff', padding: '6px 48px',
      fontSize: 12, zIndex: 99999, pointerEvents: 'none', letterSpacing: '1.2px',
    }}>
      PREVIEW
    </div>
  )
}
