// Resolves the backend base URL.
// Priority: EXPO_PUBLIC_API_URL (set in .env or EAS) -> hard-coded fallback.
// Edit FALLBACK for a quick local test if you don't want to use a .env file.
const FALLBACK = "http://192.168.1.42:8000";

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || FALLBACK).replace(/\/+$/, "");
