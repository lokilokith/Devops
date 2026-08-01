import * as React from "react"
import { Search, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

interface SearchBarProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange"> {
  onSearch: (value: string) => void
  debounceMs?: number
  isLoading?: boolean
}

export function SearchBar({
  onSearch,
  debounceMs = 300,
  isLoading,
  className,
  ...props
}: SearchBarProps) {
  const [value, setValue] = React.useState("")
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value
    setValue(newValue)

    if (timerRef.current) clearTimeout(timerRef.current)

    timerRef.current = setTimeout(() => {
      onSearch(newValue)
    }, debounceMs)
  }

  const handleClear = () => {
    setValue("")
    onSearch("")
    if (timerRef.current) clearTimeout(timerRef.current)
  }

  return (
    <div className={cn("relative flex items-center max-w-sm", className)}>
      <Search className="absolute left-2.5 h-4 w-4 text-muted-foreground" />
      <Input
        value={value}
        onChange={handleChange}
        className="pl-8 pr-10"
        {...props}
      />
      {value && !isLoading && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-1 h-7 w-7 text-muted-foreground hover:text-foreground"
          onClick={handleClear}
        >
          <X className="h-4 w-4" />
        </Button>
      )}
      {isLoading && (
        <div className="absolute right-2.5 flex items-center justify-center">
          <Spinner size={16} />
        </div>
      )}
    </div>
  )
}
