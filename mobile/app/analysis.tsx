import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable } from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";
import { colors, spacing, radius, levelColor } from "../src/theme";
import { Card, Badge, KV } from "../src/components/ui";
import { api, AnalysisResponse, Flag, Timeframe } from "../src/api";

const GREEK_ORDER = ["delta", "gamma", "theta", "vega", "rho"];
const GREEK_LABEL: Record<string, string> = {
  delta: "Delta", gamma: "Gamma", theta: "Theta", vega: "Vega", rho: "Rho",
};

export default function AnalysisScreen() {
  const params = useLocalSearchParams<{
    ticker: string; timeframe: Timeframe; flag: Flag; strike: string;
  }>();
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await api.analysis(
          params.ticker, params.timeframe, Number(params.strike), params.flag,
        );
        if (alive) setData(res);
      } catch (e: any) {
        if (alive) setError(e?.message ?? "Failed to load analysis");
      }
    })();
    return () => { alive = false; };
  }, [params.ticker, params.timeframe, params.flag, params.strike]);

  const title = `${params.ticker} $${Number(params.strike).toFixed(0)} ${params.flag === "c" ? "Call" : "Put"}`;

  if (error) {
    return (
      <View style={styles.screen}>
        <Stack.Screen options={{ title }} />
        <Card style={{ margin: spacing.lg, borderColor: colors.red }}>
          <Text style={{ color: colors.red, fontWeight: "600" }}>⚠︎ {error}</Text>
        </Card>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={[styles.screen, styles.center]}>
        <Stack.Screen options={{ title }} />
        <ActivityIndicator color={colors.accent} />
        <Text style={styles.dim}>Analyzing contract…</Text>
      </View>
    );
  }

  const riskPct = Math.max(0, Math.min(100, data.risk.score));

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 48 }}
    >
      <Stack.Screen options={{ title }} />

      {/* Header */}
      <Card>
        <Text style={styles.name}>{data.name}</Text>
        <Text style={styles.headline}>
          ${data.strike.toFixed(2)} {data.flag === "c" ? "Call" : "Put"} · Exp {data.expiration}
        </Text>
        <View style={styles.headerGrid}>
          <KV label="Spot" value={`$${data.price.toFixed(2)}`} />
          <KV label="Bid / Ask" value={`${money(data.bid)} / ${money(data.ask)}`} />
          <KV label="IV" value={data.iv != null ? `${data.iv}%` : "—"} />
        </View>
      </Card>

      {/* Risk score */}
      <Card>
        <View style={styles.riskHeader}>
          <Text style={styles.sectionTitle}>Risk Rating</Text>
          <Badge text={data.risk.level} color={data.risk.color} />
        </View>
        <Text style={[styles.riskScore, { color: data.risk.color }]}>
          {data.risk.score}
          <Text style={styles.riskScoreMax}> / 100</Text>
        </Text>
        <View style={styles.gaugeTrack}>
          <View style={[styles.gaugeFill, { width: `${riskPct}%`, backgroundColor: data.risk.color }]} />
        </View>

        {/* Component breakdown */}
        <View style={{ marginTop: spacing.md }}>
          {Object.entries(data.risk.components).map(([name, c]) => (
            <View key={name} style={{ marginBottom: 8 }}>
              <View style={styles.compRow}>
                <Text style={styles.compLabel}>{capitalize(name)}</Text>
                <Text style={styles.compVal}>{c.earned} / {c.max}</Text>
              </View>
              <View style={styles.compTrack}>
                <View
                  style={[styles.compFill, { width: `${(c.earned / c.max) * 100}%` }]}
                />
              </View>
            </View>
          ))}
        </View>

        {data.risk.drivers.length > 0 && (
          <View style={styles.drivers}>
            {data.risk.drivers.map((d, i) => (
              <Text key={i} style={styles.driverText}>• {d}</Text>
            ))}
          </View>
        )}
        {data.risk.breakeven_pct != null && (
          <Text style={[styles.dim, { marginTop: spacing.sm }]}>
            Break-even: stock must move {data.risk.breakeven_pct >= 0 ? "+" : ""}
            {data.risk.breakeven_pct.toFixed(1)}% by expiration.
          </Text>
        )}
      </Card>

      {/* Probability */}
      <Card>
        <Text style={styles.sectionTitle}>Probability of Expiring ITM</Text>
        <View style={styles.probRow}>
          <ProbBox
            label="Risk-Neutral"
            pct={data.probability.risk_neutral_pct}
            sub="Black-Scholes N(d₂)"
          />
          <ProbBox
            label="Real-World"
            pct={data.probability.real_world_pct}
            sub="Adjusted for historical drift"
          />
        </View>
      </Card>

      {/* Greek significance */}
      <Text style={styles.groupTitle}>Greeks Explained</Text>
      {GREEK_ORDER.map((key) => {
        const s = data.significance[key];
        if (!s) return null;
        const isOpen = expanded === key;
        return (
          <Card key={key}>
            <Pressable onPress={() => setExpanded(isOpen ? null : key)}>
              <View style={styles.greekHeader}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                  <Text style={styles.greekLabel}>{GREEK_LABEL[key]}</Text>
                  <Text style={styles.greekValue}>
                    {s.value != null ? s.value.toFixed(4) : "N/A"}
                  </Text>
                </View>
                {s.badge ? <Badge text={s.badge} color={levelColor(s.level)} /> : null}
              </View>
              {s.description ? <Text style={styles.greekDesc}>{s.description}</Text> : null}
              {s.headline ? (
                <Text style={[styles.greekHeadline, { color: levelColor(s.level) }]}>
                  {isOpen ? s.headline : `${s.headline}  ›`}
                </Text>
              ) : null}
              {isOpen && s.detail ? <Text style={styles.greekDetail}>{s.detail}</Text> : null}
            </Pressable>
          </Card>
        );
      })}

      <Text style={styles.disclaimer}>
        For educational purposes only. Not investment advice. Options involve substantial risk.
      </Text>
    </ScrollView>
  );
}

function ProbBox({ label, pct, sub }: { label: string; pct: number | null; sub: string }) {
  const color =
    pct == null ? colors.textDim
    : pct >= 65 ? colors.green
    : pct >= 45 ? colors.yellow
    : pct >= 25 ? colors.orange
    : colors.red;
  return (
    <View style={styles.probBox}>
      <Text style={styles.dim}>{label}</Text>
      <Text style={[styles.probPct, { color }]}>{pct != null ? `${pct}%` : "—"}</Text>
      <Text style={styles.probSub}>{sub}</Text>
    </View>
  );
}

function money(v: number | null): string {
  return v == null ? "—" : `$${v.toFixed(2)}`;
}
function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  center: { alignItems: "center", justifyContent: "center", gap: spacing.sm },
  dim: { color: colors.textDim, fontSize: 13 },
  name: { color: colors.text, fontSize: 15, fontWeight: "600" },
  headline: { color: colors.text, fontSize: 20, fontWeight: "800", marginTop: 2, marginBottom: spacing.md },
  headerGrid: { gap: 2 },
  sectionTitle: { color: colors.text, fontSize: 17, fontWeight: "700" },
  groupTitle: { color: colors.text, fontSize: 18, fontWeight: "700", marginTop: spacing.sm, marginBottom: spacing.sm },
  riskHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  riskScore: { fontSize: 44, fontWeight: "900", marginTop: 4 },
  riskScoreMax: { fontSize: 18, color: colors.textDim, fontWeight: "700" },
  gaugeTrack: {
    height: 10, backgroundColor: colors.cardAlt, borderRadius: 5, overflow: "hidden", marginTop: 6,
  },
  gaugeFill: { height: "100%", borderRadius: 5 },
  compRow: { flexDirection: "row", justifyContent: "space-between" },
  compLabel: { color: colors.textDim, fontSize: 13 },
  compVal: { color: colors.text, fontSize: 13, fontWeight: "600" },
  compTrack: { height: 5, backgroundColor: colors.cardAlt, borderRadius: 3, marginTop: 3, overflow: "hidden" },
  compFill: { height: "100%", backgroundColor: colors.accent, borderRadius: 3 },
  drivers: { marginTop: spacing.md, gap: 4 },
  driverText: { color: colors.text, fontSize: 13, lineHeight: 19 },
  probRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.sm },
  probBox: { flex: 1, backgroundColor: colors.cardAlt, borderRadius: radius.sm, padding: spacing.md },
  probPct: { fontSize: 28, fontWeight: "900", marginVertical: 2 },
  probSub: { color: colors.textDim, fontSize: 11 },
  greekHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  greekLabel: { color: colors.text, fontSize: 16, fontWeight: "700" },
  greekValue: { color: colors.textDim, fontSize: 15, fontWeight: "600" },
  greekDesc: { color: colors.textDim, fontSize: 12, lineHeight: 17 },
  greekHeadline: { fontSize: 13, fontWeight: "700", marginTop: 6 },
  greekDetail: { color: colors.text, fontSize: 13, lineHeight: 20, marginTop: 6 },
  disclaimer: { color: colors.textDim, fontSize: 11, textAlign: "center", marginTop: spacing.md, lineHeight: 16 },
});
