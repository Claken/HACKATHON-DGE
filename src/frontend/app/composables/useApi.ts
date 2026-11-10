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

export interface HistoryEntry {
  date: string;
  passages_jour: number;
}

export type TrainStatus = "idle" | "training" | "done" | "error";

export interface TrainStatusResponse {
  status: TrainStatus;
  ready: boolean;
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

  async function fetchHistory(siteId: string, from: string, to: string): Promise<HistoryEntry[]> {
    return $fetch<HistoryEntry[]>(`${base}/history/${siteId}`, {
      params: { from, to },
    });
  }

  async function triggerTrain(siteId: string): Promise<{ status: string }> {
    return $fetch<{ status: string }>(`${base}/train/${siteId}`, { method: "POST" });
  }

  async function fetchTrainStatus(siteId: string): Promise<TrainStatusResponse> {
    return $fetch<TrainStatusResponse>(`${base}/train/${siteId}/status`);
  }

  return { fetchSites, fetchPredict, fetchHistory, triggerTrain, fetchTrainStatus };
}
