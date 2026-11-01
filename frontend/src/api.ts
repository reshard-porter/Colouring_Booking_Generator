// Thin API client. Every mutating request carries X-CBS-Client (CSRF guard on the server).
export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, message: string, data?: any) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request<T = any>(method: string, url: string, body?: any): Promise<T> {
  const init: RequestInit = { method, headers: { "X-CBS-Client": "1" } };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError(0, "Cannot reach the local Coloring Book Studio server. Is it running?");
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) throw new ApiError(res.status, (data && data.detail) || `Request failed (${res.status})`, data);
  return data as T;
}

export const api = {
  get: <T = any>(u: string) => request<T>("GET", u),
  post: <T = any>(u: string, b: any = {}) => request<T>("POST", u, b),
  put: <T = any>(u: string, b: any) => request<T>("PUT", u, b),
  patch: <T = any>(u: string, b: any) => request<T>("PATCH", u, b),
  del: <T = any>(u: string) => request<T>("DELETE", u),
  upload: <T = any>(u: string, form: FormData) => request<T>("POST", u, form),
};

export const img = (versionId: string, max = 400) => `/api/versions/${versionId}/image?max=${max}`;

export function fmtIn(v: number, d = 3) {
  return `${(+v).toFixed(d).replace(/\.?0+$/, "")} in`;
}
