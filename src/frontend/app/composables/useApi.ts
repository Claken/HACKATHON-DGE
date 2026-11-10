export interface SiteInfo {
  id: string;
  nom: string;
  commune?: string;
  has_data: boolean;
  ready: boolean;
}

export interface DayForecast {
  date: string;
  passages_prevus: number;
  pic_horaire_estime: number;
  passages_reference: number;
  precipitations_mm: number;
  risque: string;
  jour_ferie: boolean;
  vacances: boolean;
}

export interface PredictResponse {
  capacite: number;
  seuils_abs: { modere: number; eleve: number };
  predictions: DayForecast[];
}

export function useApi() {
  const config = useRuntimeConfig();
  const base = config.public.apiBase as string;

  async function fetchSites(): Promise<SiteInfo[]> {
    return $fetch<SiteInfo[]>(`${base}/sites`);
  }

  async function fetchPredict(siteId: string): Promise<PredictResponse> {
    return $fetch<PredictResponse>(`${base}/predict/${siteId}`);
  }

  return { fetchSites, fetchPredict };
}
