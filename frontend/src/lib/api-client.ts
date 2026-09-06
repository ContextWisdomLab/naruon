import { ANONYMOUS_SESSION_CLAIMS, type SessionClaims } from "./session-cookie";

const CLIENT_CONTROLLED_AUTHORITY_HEADERS = new Set([
  'authorization',
  'x-dev-auth-token',
  'x-group-id',
  'x-group-ids',
  'x-organization-id',
  'x-user-id',
  'x-user-role',
]);

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || (typeof window !== 'undefined' ? '' : 'http://localhost:8000');
  }

  setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  getBaseUrl() {
    return this.baseUrl;
  }

  private getHeaders(init?: RequestInit): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...this.getSafeCallerHeaders(init?.headers),
    };
    return headers;
  }

  private getFormHeaders(init?: RequestInit): HeadersInit {
    const headers: Record<string, string> = this.getSafeCallerHeaders(init?.headers);
    Object.keys(headers).forEach((name) => {
      if (name.toLowerCase() === 'content-type') {
        delete headers[name];
      }
    });
    return headers;
  }

  private getSafeCallerHeaders(headers?: HeadersInit): Record<string, string> {
    const safeHeaders: Record<string, string> = {};
    const includeHeader = (name: string, value: string) => {
      if (CLIENT_CONTROLLED_AUTHORITY_HEADERS.has(name.toLowerCase())) return;
      safeHeaders[name] = value;
    };

    if (!headers) return safeHeaders;
    if (typeof Headers !== 'undefined' && headers instanceof Headers) {
      headers.forEach((value, name) => includeHeader(name, value));
      return safeHeaders;
    }
    if (Array.isArray(headers)) {
      headers.forEach(([name, value]) => includeHeader(name, value));
      return safeHeaders;
    }

    Object.entries(headers).forEach(([name, value]) => includeHeader(name, value));
    return safeHeaders;
  }

  getSessionClaims(): SessionClaims {
    return ANONYMOUS_SESSION_CLAIMS;
  }

  async getServerSessionClaims(): Promise<SessionClaims> {
    try {
      const response = await fetch('/auth/session', {
        method: 'GET',
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      if (!response.ok) return ANONYMOUS_SESSION_CLAIMS;

      const body = await response.json() as { authenticated?: unknown; claims?: Partial<SessionClaims> };
      if (body.authenticated !== true) return ANONYMOUS_SESSION_CLAIMS;
      const claims = body.claims ?? {};
      return {
        userId: typeof claims.userId === 'string' ? claims.userId : null,
        organizationId: typeof claims.organizationId === 'string' ? claims.organizationId : null,
        workspaceId: typeof claims.workspaceId === 'string' ? claims.workspaceId : null,
      };
    } catch {
      return ANONYMOUS_SESSION_CLAIMS;
    }
  }

  getCurrentUserId() {
    return this.getSessionClaims().userId;
  }

  private createApiError(status?: number) {
    const error = new Error("API request failed") as Error & { status?: number };
    error.name = "ApiClientError";
    error.status = status;
    error.stack = undefined;
    return error;
  }

  private async fetchApi(endpoint: string, init: RequestInit) {
    try {
      return await fetch(`${this.baseUrl}${endpoint}`, init);
    } catch {
      throw this.createApiError();
    }
  }

  private async parseOptionalJson<T>(response: Response): Promise<T> {
    const text = await response.text();
    return text ? JSON.parse(text) : ({} as T);
  }

  async get<T>(endpoint: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchApi(endpoint, {
      ...init,
      credentials: init?.credentials ?? 'same-origin',
      headers: this.getHeaders(init),
    });
    if (!response.ok) {
      throw this.createApiError(response.status);
    }
    return response.json();
  }

  async post<T>(endpoint: string, body: unknown, init?: RequestInit): Promise<T> {
    const response = await this.fetchApi(endpoint, {
      ...init,
      method: 'POST',
      credentials: init?.credentials ?? 'same-origin',
      headers: this.getHeaders(init),
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw this.createApiError(response.status);
    }
    return response.json();
  }

  async postForm<T>(endpoint: string, body: FormData, init?: RequestInit): Promise<T> {
    const response = await this.fetchApi(endpoint, {
      ...init,
      method: 'POST',
      credentials: init?.credentials ?? 'same-origin',
      headers: this.getFormHeaders(init),
      body,
    });
    if (!response.ok) {
      throw this.createApiError(response.status);
    }
    return response.json();
  }

  async put<T>(endpoint: string, body: unknown, init?: RequestInit): Promise<T> {
    const response = await this.fetchApi(endpoint, {
      ...init,
      method: 'PUT',
      credentials: init?.credentials ?? 'same-origin',
      headers: this.getHeaders(init),
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw this.createApiError(response.status);
    }
    return this.parseOptionalJson<T>(response);
  }

  async patch<T>(endpoint: string, body: unknown, init?: RequestInit): Promise<T> {
    const response = await this.fetchApi(endpoint, {
      ...init,
      method: 'PATCH',
      credentials: init?.credentials ?? 'same-origin',
      headers: this.getHeaders(init),
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw this.createApiError(response.status);
    }
    return response.json();
  }

  async delete<T>(endpoint: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchApi(endpoint, {
      ...init,
      method: 'DELETE',
      credentials: init?.credentials ?? 'same-origin',
      headers: this.getHeaders(init),
    });
    if (!response.ok) {
      throw this.createApiError(response.status);
    }
    return this.parseOptionalJson<T>(response);
  }
}

export const apiClient = new ApiClient();
