import { useQuery } from "@tanstack/react-query"
import { vaultService } from "../api/vault.service"

export const vaultKeys = {
  all: ["vault"] as const,
  secrets: () => [...vaultKeys.all, "secrets"] as const,
  stats: () => [...vaultKeys.all, "stats"] as const,
}

export function useVaultSecrets() {
  return useQuery({
    queryKey: vaultKeys.secrets(),
    queryFn: vaultService.getSecrets,
  })
}

export function useVaultStats() {
  return useQuery({
    queryKey: vaultKeys.stats(),
    queryFn: vaultService.getStats,
  })
}
