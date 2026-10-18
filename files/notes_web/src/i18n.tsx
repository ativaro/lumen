import { useSyncExternalStore } from "react";
import english from "./en.json";
type Language = "de" | "en";
let language: Language = "de";
try {
  language = localStorage.getItem("lumen-language") === "en" ? "en" : "de";
} catch {}
const listeners = new Set<() => void>();
function subscribe(callback: () => void) {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}
export function useLanguage() {
  return useSyncExternalStore(subscribe, () => language);
}
export function locale() {
  return language === "de" ? "de-CH" : "en-GB";
}
export function tr(text: string | undefined) {
  if (!text) return "";
  if (language === "de") return text;
  const key = text.trim();
  const translated = (english as Record<string, string>)[key];
  return translated ? text.replace(key, translated) : text;
}
export function choose(value: Language, publish = true) {
  language = value;
  document.documentElement.lang = value;
  try {
    localStorage.setItem("lumen-language", value);
  } catch {}
  for (const notify of listeners) notify();
  if (publish) window.dispatchEvent(new CustomEvent("lumen-language-change", { detail: value }));
}
export function LanguageSwitch() {
  const value = useLanguage();
  return (
    <select
      className="language-switch"
      aria-label="Sprache / Language"
      value={value}
      onChange={(e) => choose(e.target.value as Language)}
    >
      <option value="de">Deutsch</option>
      <option value="en">English</option>
    </select>
  );
}
document.documentElement.lang = language;
