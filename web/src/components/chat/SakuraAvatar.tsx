interface SakuraAvatarProps {
  spinning?: boolean
  size?: 'sm' | 'md' | 'lg'
}

const sizeMap = {
  sm: 'w-8 h-8',
  md: 'w-9 h-9',
  lg: 'w-11 h-11',
}

export default function SakuraAvatar({ spinning = false, size = 'md' }: SakuraAvatarProps) {
  return (
    <div
      className={`sakura-avatar ${sizeMap[size]} ${spinning ? 'sakura-spinning' : ''}`}
      aria-hidden="true"
    >
      <span /><span /><span /><span /><span />
    </div>
  )
}
