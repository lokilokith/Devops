export interface VaultSecretMetadata {
  key_version: string;
  algorithm: string;
  created_at: string;
}

export interface VaultSecret {
  id: string;
  resource_id: string;
  status: string;
  row_version: number;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  // If backend returns populated resource data:
  resource?: {
    id: string;
    resource_name: string;
    resource_code: string;
    resource_type: string;
  };
}

export interface SecretRevealResponse {
  id: string;
  payload: string;
  metadata: VaultSecretMetadata;
}

export interface VaultStats {
  total: number;
  active: number;
  disabled: number;
}
