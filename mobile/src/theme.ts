// Central dark theme for Options Guru. Colors mirror the original Streamlit app.
export const colors = {
  bg: "#0B0F14",
  card: "#141B24",
  cardAlt: "#1B2531",
  border: "#243040",
  text: "#E8EDF2",
  textDim: "#8A99A8",
  accent: "#2196F3",
  accentSector: "#FF9800",
  accentMarket: "#4CAF50",
  // Significance / risk level colors (shared with backend)
  low: "#9E9E9E",
  normal: "#4CAF50",
  notable: "#2196F3",
  high: "#FF9800",
  extreme: "#F44336",
  green: "#4CAF50",
  yellow: "#FFC107",
  orange: "#FF9800",
  red: "#F44336",
};

// Map a "level" string from the backend to a color.
export function levelColor(level?: string | null): string {
  switch (level) {
    case "low": return colors.low;
    case "normal": return colors.normal;
    case "notable": return colors.notable;
    case "high": return colors.high;
    case "extreme": return colors.extreme;
    default: return colors.textDim;
  }
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const radius = { sm: 8, md: 12, lg: 16 };
