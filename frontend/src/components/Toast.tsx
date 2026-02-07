import { useEffect, useState } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react'

interface ToastProps {
  id: number
  message: string
  type: 'success' | 'error' | 'warning' | 'info'
  onClose: (id: number) => void
  duration?: number
}

const config = {
  success: {
    icon: CheckCircle,
    bg: 'bg-green-50 border-green-200',
    text: 'text-green-800',
    iconColor: 'text-green-500',
  },
  error: {
    icon: XCircle,
    bg: 'bg-red-50 border-red-200',
    text: 'text-red-800',
    iconColor: 'text-red-500',
  },
  warning: {
    icon: AlertTriangle,
    bg: 'bg-amber-50 border-amber-200',
    text: 'text-amber-800',
    iconColor: 'text-amber-500',
  },
  info: {
    icon: Info,
    bg: 'bg-blue-50 border-blue-200',
    text: 'text-blue-800',
    iconColor: 'text-blue-500',
  },
}

export default function Toast({ id, message, type, onClose, duration = 5000 }: ToastProps) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Trigger enter animation
    requestAnimationFrame(() => setVisible(true))

    const timer = setTimeout(() => {
      setVisible(false)
      setTimeout(() => onClose(id), 300)
    }, duration)

    return () => clearTimeout(timer)
  }, [id, duration, onClose])

  const { icon: Icon, bg, text, iconColor } = config[type]

  return (
    <div
      className={`pointer-events-auto border rounded-lg p-4 shadow-lg transition-all duration-300 ${bg} ${
        visible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'
      }`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <Icon className={`h-5 w-5 flex-shrink-0 mt-0.5 ${iconColor}`} />
        <p className={`text-sm flex-1 ${text}`}>{message}</p>
        <button
          onClick={() => {
            setVisible(false)
            setTimeout(() => onClose(id), 300)
          }}
          className={`flex-shrink-0 ${text} opacity-60 hover:opacity-100`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
