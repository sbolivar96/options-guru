import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  ScrollView,
  Pressable,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, radius } from "../../src/theme";
import { Card, Segmented, Button } from "../../src/components/ui";
import { api, ChainResponse, ChainRow, Flag, Timeframe } from "../../src/api";

const TIMEFRAMES: { label: string; value: Timeframe }[] = [
  { label: "5 Days", value: "5d" },
  { label: "1 Month", value: "1m" },
  { label: "3 Months", value: "3m" },
];

function moneynessColor(m: string | null): string {
  if (m === "ITM") return colors.green;
  if (m === "ATM") return colors.yellow;
  return colors.textDim;
}

export default function AnalyzeScreen() {
  const router = useRouter();
  const [ticker, setTicker] = useState("AAPL");
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");
  const [flag, setFlag] = useState<Flag>("c");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chain, setChain] = useState<ChainResponse | null>(null);

  async function load() {
    const sym = ticker.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.chain(sym, timeframe, flag);
      setChain(data);
    } catch (e: any) {
      setError(e?.message ?? "Something went wrong");
      setChain(null);
    } finally {
      setLoading(false);
    }
  }

  function openAnalysis(row: ChainRow) {
    if (!chain) return;
    router.push({
      pathname: "/analysis",
      params: { ticker: chain.ticker, timeframe, flag, strike: String(row.strike) },
    });
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        style={styles.screen}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 48 }}
        keyboardShouldPersistTaps="handled"
      >
        <Card>
          <Text style={styles.label}>Ticker</Text>
          <TextInput
            value={ticker}
            onChangeText={setTicker}
            autoCapitalize="characters"
            autoCorrect={false}
            placeholder="e.g. AAPL"
            placeholderTextColor={colors.textDim}
            style={styles.input}
            returnKeyType="search"
            onSubmitEditing={load}
          />

          <Text style={[styles.label, { marginTop: spacing.md }]}>Timeframe</Text>
          <Segmented options={TIMEFRAMES} value={timeframe} onChange={setTimeframe} />

          <Text style={[styles.label, { marginTop: spacing.md }]}>Type</Text>
          <Segmented
            options={[
              { label: "Calls", value: "c" as Flag },
              { label: "Puts", value: "p" as Flag },
            ]}
            value={flag}
            onChange={setFlag}
          />

          <View style={{ height: spacing.md }} />
          <Button title={loading ? "Loading…" : "Analyze"} onPress={load} disabled={loading} />
        </Card>

        {loading && (
          <View style={styles.center}>
            <ActivityIndicator color={colors.accent} />
            <Text style={styles.dim}>Fetching live options data…</Text>
          </View>
        )}

        {error && (
          <Card style={{ borderColor: colors.red }}>
            <Text style={{ color: colors.red, fontWeight: "600" }}>⚠︎ {error}</Text>
          </Card>
        )}

        {chain && !loading && (
          <>
            <Card>
              <Text style={styles.stockName}>{chain.name}</Text>
              <View style={styles.priceRow}>
                <Text style={styles.price}>${chain.price.toFixed(2)}</Text>
                <View style={styles.expPill}>
                  <Text style={styles.expText}>
                    {flag === "c" ? "Calls" : "Puts"} · Exp {chain.expiration}
                  </Text>
                </View>
              </View>
              {chain.sector ? <Text style={styles.dim}>{chain.sector}</Text> : null}
            </Card>

            <Text style={styles.chainHeaderTitle}>Options Chain</Text>
            <Text style={[styles.dim, { marginBottom: spacing.sm }]}>
              Tap a strike for full risk analysis
            </Text>

            <Card style={{ padding: 0 }}>
              <View style={[styles.rowHeader]}>
                <Text style={[styles.hCell, { flex: 1.2 }]}>Strike</Text>
                <Text style={[styles.hCell, styles.num]}>Delta</Text>
                <Text style={[styles.hCell, styles.num]}>IV%</Text>
                <Text style={[styles.hCell, styles.num]}>P(ITM)</Text>
                <Ionicons name="chevron-forward" size={14} color="transparent" />
              </View>
              {chain.rows.map((row, i) => (
                <Pressable
                  key={row.strike}
                  onPress={() => openAnalysis(row)}
                  style={({ pressed }) => [
                    styles.row,
                    i % 2 === 1 && { backgroundColor: colors.cardAlt },
                    pressed && { backgroundColor: colors.border },
                  ]}
                >
                  <View style={{ flex: 1.2, flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={styles.strike}>${row.strike.toFixed(2)}</Text>
                    {row.moneyness ? (
                      <Text style={[styles.moneyness, { color: moneynessColor(row.moneyness) }]}>
                        {row.moneyness}
                      </Text>
                    ) : null}
                  </View>
                  <Text style={[styles.cell, styles.num]}>{fmt(row.delta, 3)}</Text>
                  <Text style={[styles.cell, styles.num]}>{fmt(row.iv, 1)}</Text>
                  <Text style={[styles.cell, styles.num]}>{row.p_itm != null ? `${row.p_itm}%` : "—"}</Text>
                  <Ionicons name="chevron-forward" size={14} color={colors.textDim} />
                </Pressable>
              ))}
            </Card>
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function fmt(v: number | null, digits: number): string {
  return v == null ? "—" : v.toFixed(digits);
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  label: { color: colors.textDim, fontSize: 13, marginBottom: 6, fontWeight: "600" },
  input: {
    backgroundColor: colors.cardAlt,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    fontSize: 18,
    fontWeight: "700",
    letterSpacing: 1,
  },
  center: { alignItems: "center", padding: spacing.xl, gap: spacing.sm },
  dim: { color: colors.textDim, fontSize: 13 },
  stockName: { color: colors.text, fontSize: 16, fontWeight: "600", marginBottom: 4 },
  priceRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  price: { color: colors.text, fontSize: 30, fontWeight: "800" },
  expPill: {
    backgroundColor: colors.cardAlt,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 10,
  },
  expText: { color: colors.textDim, fontSize: 12, fontWeight: "600" },
  chainHeaderTitle: { color: colors.text, fontSize: 18, fontWeight: "700", marginTop: spacing.sm },
  rowHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    gap: 6,
  },
  hCell: { color: colors.textDim, fontSize: 12, fontWeight: "700", flex: 1 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    gap: 6,
  },
  cell: { color: colors.text, fontSize: 14, flex: 1 },
  num: { textAlign: "right" },
  strike: { color: colors.text, fontSize: 15, fontWeight: "700" },
  moneyness: { fontSize: 10, fontWeight: "700" },
});
