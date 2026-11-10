<script setup lang="ts">
import { formatDate, offsetDate, levelLabels } from "~/utils/forecast";
const {
  anchor,
  siteId,
  site,
  sites,
  week,
  lastWeek,
  cards,
  selectedDate,
  selected,
  thresholds,
  periodLabel,
  loading,
  error,
  today,
  trainStatus,
  trainSite,
} = useDashboard();
const longDate = (date: string) =>
  formatDate(date, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

const isTraining = computed(() => trainStatus.value === "training");
const isTrainError = computed(() => trainStatus.value === "error");
function goToHerretang() {
  siteId.value = "herretang";
  today();
}
const trainLabel = computed(() => {
  if (trainStatus.value === "training") return "Entraînement en cours…";
  if (trainStatus.value === "done") return "Modèle prêt — rechargement…";
  return "Entraîner le modèle";
});
</script>
<template>
  <SiteHeader :site-name="site.name" />
  <div v-if="error" role="alert" class="api-error">
    {{ error }}
  </div>
  <main>
    <div v-if="loading" class="loading" aria-live="polite">Chargement des prévisions…</div>
    <div class="context">
      <div class="site-picker">
        <label for="site">Site touristique</label
        ><select id="site" v-model="siteId">
          <option v-for="item in sites" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
      </div>
      <nav class="week-controls" aria-label="Navigation par semaine">
        <button
          class="week-arrow"
          :disabled="week <= -52"
          aria-label="Semaine précédente"
          @click="week--"
        >
          ‹
        </button>
        <div class="week-caption">
          <span>Semaine du lundi au dimanche</span
          ><strong>{{ periodLabel }}</strong>
        </div>
        <button
          class="week-arrow"
          :disabled="week >= lastWeek"
          aria-label="Semaine suivante"
          @click="week++"
        >
          ›</button
        ><button v-if="week !== 0" class="today-button" @click="today">
          Revenir à aujourd’hui
        </button>
      </nav>
    </div>
    <WeekOverview
      :cards="cards"
      :selected="selectedDate"
      :connected="site.available"
      @select="selectedDate = $event"
    />
    <p class="horizon-note">
      Prévisions jusqu’au {{ formatDate(offsetDate(anchor, 6)) }} inclus · 7
      jours à compter d’aujourd’hui
    </p>
    <!-- Détail prévision (jours futurs) -->
    <template v-if="selected?.forecast && selected.level">
      <div class="selected-day-heading">
        <span>Détail de la journée</span
        ><strong>{{ longDate(selected.date) }}</strong>
      </div>
      <section class="summary-grid">
        <div class="metric">
          <span class="muted small">Vigilance prévisionnelle</span>
          <div class="value">{{ levelLabels[selected.level] }}</div>
          <span class="small"
            ><i class="dot" :class="selected.level" />{{
              selected.level === "low"
                ? "Pas de dépassement prévu"
                : "À surveiller autour de 14 h"
            }}</span
          >
        </div>
        <div class="metric">
          <span class="muted small">Passages prévus sur la journée</span>
          <div class="value">
            {{ selected.forecast.total }} <small>passages</small>
          </div>
          <span class="muted small"
            >{{ site.name }} · passages entrants</span
          >
        </div>
        <div class="metric">
          <span class="muted small">Météo de la journée</span>
          <div class="value weather">
            {{ selected.forecast.rain === 0 ? "☀ Temps sec" : "☂ Pluie" }}
          </div>
          <span class="muted small"
            >{{ selected.forecast.rain.toLocaleString("fr-FR") }} mm de
            précipitations · Neige : 0 cm</span
          >
        </div>
      </section>
      <HourlyChart
        :peak="selected.forecast.peak"
        :total="selected.forecast.total"
        :reference="selected.forecast.reference"
        :threshold="thresholds.moderate"
        :date="longDate(selected.date)"
      />
    </template>

    <!-- Détail historique (jours passés avec données CSV) -->
    <template v-else-if="selected?.historical !== null && selected?.historical !== undefined && selected.level">
      <div class="selected-day-heading">
        <span>Données observées</span
        ><strong>{{ longDate(selected.date) }}</strong>
      </div>
      <section class="summary-grid">
        <div class="metric">
          <span class="muted small">Niveau de fréquentation</span>
          <div class="value">{{ levelLabels[selected.level] }}</div>
          <span class="small"><i class="dot" :class="selected.level" />Comptage réel · source CSV</span>
        </div>
        <div class="metric">
          <span class="muted small">Passages observés sur la journée</span>
          <div class="value">
            {{ selected.historical }} <small>passages</small>
          </div>
          <span class="muted small">{{ site.name }} · passages entrants</span>
        </div>
      </section>
    </template>

    <!-- Aucune donnée disponible pour la période -->
    <section v-else class="empty">
      <h2>
        {{
          site.available
            ? "Aucune donnée historique connectée"
            : "Prévisions non connectées"
        }}
      </h2>
      <p>
        {{
          site.available
            ? "Cette période est passée. Les comptages observés restent à connecter."
            : `Le site ${site.name} est sélectionné. Ses prévisions restent à connecter.`
        }}
      </p>
      <template v-if="!site.available && site.has_data">
        <button
          class="today-button"
          :disabled="isTraining"
          @click="trainSite"
        >
          {{ trainLabel }}
        </button>
        <p v-if="isTrainError" class="muted small" style="margin-top:.5rem">
          Erreur durant l’entraînement. Vérifiez les logs de l’API.
        </p>
      </template>
      <button v-else class="today-button" @click="goToHerretang">
        Revenir à l’Herretang · aujourd’hui
      </button>
    </section>
    <ThresholdSettings v-model="thresholds" />
    <details class="sources">
      <summary>Sources, fiabilité et limites</summary>
      <p>
        Prévisions fournies par le modèle XGBoost de l’équipe 2. La courbe
        horaire est illustrative (répartition type) et non issue du modèle journalier.
      </p>
      <p>
        Les passages entrants à un accès ne représentent ni des visiteurs
        uniques, ni une occupation simultanée. Les autres sites et l’historique
        ne sont pas connectés.
      </p>
      <p>
        Calendriers : jours fériés métropolitains et vacances scolaires
        Grenoble, zone A (instantanés officiels 2025–2027 pour les vacances ; à
        actualiser). Aucun service de notification n’est connecté.
      </p>
    </details>
    <footer>
      Prévisions XGBoost · Météo Open-Meteo · Hackathon DGE · Équipe 2
    </footer>
  </main>
</template>
