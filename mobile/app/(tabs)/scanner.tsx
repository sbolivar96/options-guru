import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { colors, spacing, radius } from "../../src/theme";
import { Card, Button, Badge } from "../../src/components/ui";
import { api, ScanRow } from "../../src/api";

function scoreColor(score: number): string {
  if (score < 20) return "#4CAF50";
  if (score < 35) return "#8BC34A";
  if (score < 50) return "#FFC107";
  if (score < 65) return "#FF9800";
  if (score < 80) return "#FF5722";
  return "#F44336";
}

export default function ScannerScreen() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<ScanRow[] | null>(null);

  async function runScan() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.scan(40);
      setRows(res.results);
    } catch (e: any) {
      setError(e?.message ?? "Scan failed");
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 48 }}
    >
      <Card>
        <Text style={styles.title}>S&P 500 Risk Scanner</Text>
        <Text style={styles.dim}>
          Scans ~40 large-cap names for their at-the-money 1-month option risk, ranked
          lowest-risk first. Live data — this can take up to a minute.
        </Text>
        <View style={{ height: spacing.md }} />
        <Button title={loading ? "Scanning…" : "Run Scan"} onPress={runScan} disabled={loading} />
      </Card>

      {loading && (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
          <Text style={styles.dim}>Crunching options chains across the index…</Text>
        </View>
      )}

      {error && (
        <Card style={{ borderColor: colors.red }}>
          <Text style={{ color: colors.red, fontWeight: "600" }}>⚠︎ {error}</Text>
        </Card>
      )}

      {rows && !loading && (
        <Card style={{ padding: 0 }}>
          {rows.length === 0 && (
            <Text style={[styles.dim, { padding: spacing.lg }]}>No results returned.</Text>
          )}
          {rows.map((r, i) => (
            <View
              key={r.ticker}
              style={[styles.row, i % 2 === 1 && { backgroundColor: colors.cardAlt }]}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.ticker}>{r.ticker}</Text>
                <Text style={styles.rowSub} numberOfLines={1}>
                  ${r.price.toFixed(2)} · {r.sector}
                </Text>
              </View>
              <View style={styles.scoreCol}>
                <Text style={[styles.scoreNum, { color: scoreColor(r.avg_score) }]}>
                  {r.avg_score}
                </Text>
                <Text style={styles.rowSub}>avg risk</Text>
              </View>
              <View style={styles.levelCol}>
                <View style={{ flexDirection: "row", gap: 4, marginBottom: 3 }}>
                  <Text style={styles.miniTag}>C {r.call_score}</Text>
                  <Text style={styles.miniTag}>P {r.put_score}</Text>
                </View>
                <Text style={styles.rowSub}>IV {r.iv_pct}%</Text>
              </View>
            </View>
          ))}
        </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  title: { color: colors.text, fontSize: 18, fontWeight: "700", marginBottom: 6 },
  dim: { color: colors.textDim, fontSize: 13, lineHeight: 18 },
  center: { alignItems: "center", padding: spacing.xl, gap: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", padding: spacing.md, gap: spacing.md },
  ticker: { color: colors.text, fontSize: 16, fontWeight: "800" },
  rowSub: { color: colors.textDim, fontSize: 11 },
  scoreCol: { alignItems: "center", width: 56 },
  scoreNum: { fontSize: 22, fontWeight: "900" },
  levelCol: { alignItems: "flex-end", width: 84 },
  miniTag: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "700",
    backgroundColor: colors.border,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
    overflow: "hidden",
  },
});
