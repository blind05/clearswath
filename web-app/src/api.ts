// Calls to the FastAPI app. Free reads (the demo) go straight through; anything that spends model credits
// sends the access code, and a 401 asks for it once, then keeps it in this browser.
const CODE_KEY = "clearswath-code";

let askForCode: () => Promise<string | null> = async () => null;
export function onCodeNeeded(ask: () => Promise<string | null>) { askForCode = ask; }

function storedCode(): string {
  try { return localStorage.getItem(CODE_KEY) || ""; } catch { return ""; }
}

async function send(url: string, init: RequestInit = {}, paid = false): Promise<Response> {
  const go = () => fetch(url, paid ? { ...init, headers: { ...(init.headers || {}), "X-Access-Code": storedCode() } } : init);
  let res = await go();
  if (paid && res.status === 401) {
    const code = await askForCode();
    if (code) {
      try { localStorage.setItem(CODE_KEY, code.trim()); } catch { /* private mode: ask again next time */ }
      res = await go();
    }
  }
  return res;
}

export async function json<T>(url: string, init: RequestInit = {}, paid = false): Promise<T> {
  const res = await send(url, init, paid);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `The request failed (${res.status}). Try again.`);
  return body as T;
}

export const post = <T>(url: string, body: FormData) => json<T>(url, { method: "POST", body }, true);
