import { useState } from "react";

export function useToast() {
  const [toasts, setToasts] = useState<any[]>([]);

  const toast = (options: any) => {
    setToasts([...toasts, options]);
    console.log("Toast:", options);
  };

  return { toast, toasts };
}
