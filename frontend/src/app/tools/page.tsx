"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Play,
  Power,
  RefreshCw,
  SlidersHorizontal,
  Wrench,
} from "lucide-react";

interface ToolInfo {
  code: string;
  name: string;
  description: string;
  category: string;
  parameters?: Record<string, unknown>;
  is_active?: boolean;
}

interface ExecuteResponse {
  status: string;
  result: unknown;
  message?: string;
  error_code?: string;
}

function parameterIsOptional(descriptor: unknown) {
  return Boolean(
    descriptor &&
    typeof descriptor === "object" &&
    "required" in descriptor &&
    (descriptor as { required?: unknown }).required === false
  );
}

function buildDefaultParameters(tool: ToolInfo) {
  return Object.fromEntries(
    Object.entries(tool.parameters ?? {})
      .filter(([, descriptor]) => !parameterIsOptional(descriptor))
      .map(([key, descriptor]) => [key, defaultParameterValue(descriptor)]),
  );
}

function defaultParameterValue(descriptor: unknown) {
  const type =
    typeof descriptor === "string"
      ? descriptor
      : descriptor && typeof descriptor === "object" && "type" in descriptor
        ? String((descriptor as { type?: unknown }).type)
        : "string";
  switch (type.toLowerCase()) {
    case "number":
    case "integer":
      return 0;
    case "boolean":
      return false;
    case "array":
      return [];
    case "object":
      return {};
    default:
      return "";
  }
}

function parameterInputValue(value: unknown, type: string) {
  if (type === "array" || type === "object") {
    return typeof value === "string" ? value : JSON.stringify(value);
  }
  if (type === "boolean") return Boolean(value);
  return String(value ?? "");
}

function parameterValueFromInput(value: string, type: string) {
  switch (type) {
    case "number":
      return value === "" ? "" : Number(value);
    case "integer":
      if (value === "") return "";
      return Number.isInteger(Number(value)) ? Number(value) : value;
    case "boolean":
      return value === "true";
    case "array":
    case "object":
      try {
        return JSON.parse(value);
      } catch {
        return value;
      }
    default:
      return value;
  }
}

function parameterTypeLabel(descriptor: unknown) {
  if (typeof descriptor === "string") return descriptor;
  if (descriptor && typeof descriptor === "object" && "type" in descriptor) {
    return String((descriptor as { type?: unknown }).type ?? "string");
  }
  return "string";
}

function parameterType(descriptor: unknown) {
  return parameterTypeLabel(descriptor).toLowerCase();
}

function parameterMaxLength(descriptor: unknown) {
  if (!descriptor || typeof descriptor !== "object" || !("max_length" in descriptor)) {
    return undefined;
  }
  const maxLength = (descriptor as { max_length?: unknown }).max_length;
  return typeof maxLength === "number" && Number.isInteger(maxLength) && maxLength >= 0
    ? maxLength
    : undefined;
}

function parameterValueMatchesType(value: unknown, descriptor: unknown) {
  switch (parameterType(descriptor)) {
    case "string":
      return typeof value === "string";
    case "number":
      return typeof value === "number" && Number.isFinite(value);
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "boolean":
      return typeof value === "boolean";
    case "array":
      return Array.isArray(value);
    case "object":
      return value !== null && typeof value === "object" && !Array.isArray(value);
    default:
      return true;
  }
}

function buildParameterValues(
  tool: ToolInfo,
  currentValues: Record<string, unknown> = {},
) {
  const parameters = tool.parameters ?? {};
  const retainedValues = Object.fromEntries(
    Object.entries(currentValues).filter(([key, value]) => (
      key in parameters && parameterValueMatchesType(value, parameters[key])
    )),
  );
  return { ...buildDefaultParameters(tool), ...retainedValues };
}

function resultTone(status: string) {
  return status === "success"
    ? "border-green-200 bg-green-50 text-green-700 dark:border-green-500/30 dark:bg-green-500/15 dark:text-green-200"
    : "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/15 dark:text-red-200";
}

function resultLabel(status: string) {
  return status === "success" ? "성공" : "실패";
}

function failureAction(errorCode?: string) {
  switch (errorCode) {
    case "tool_parameter_too_long":
      return "입력 길이를 줄인 뒤 다시 실행하세요.";
    case "invalid_json":
      return "JSON 형식을 확인한 뒤 다시 실행하세요.";
    case "invalid_url_encoding":
      return "URL 인코딩을 확인한 뒤 다시 실행하세요.";
    case "missing_tool_parameter":
    case "invalid_tool_parameter_type":
    case "unexpected_tool_parameters":
      return "입력 항목과 형식을 확인한 뒤 다시 실행하세요.";
    default:
      return errorCode ? "잠시 후 다시 실행하세요." : "";
  }
}

function resultMessage(response: ExecuteResponse) {
  if (response.status === "success") {
    return typeof response.result === "string"
      ? response.result
      : JSON.stringify(response.result) ?? "실행 결과가 없습니다.";
  }
  const message = response.message || JSON.stringify(response.result) || "실행 결과가 없습니다.";
  const action = failureAction(response.error_code);
  return action ? `${message} ${action}` : message;
}

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [executing, setExecuting] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<Record<string, ExecuteResponse>>({});
  const [parameterValues, setParameterValues] = useState<Record<string, Record<string, unknown>>>({});

  useEffect(() => {
    let isMounted = true;
    apiClient.get<ToolInfo[]>("/api/tools")
      .then((data) => {
        if (isMounted) {
          setTools(data);
          setParameterValues((currentValues) =>
            Object.fromEntries(
              data.map((tool) => [
                tool.code,
                buildParameterValues(tool, currentValues[tool.code]),
              ]),
            ),
          );
          setLoadError(false);
          setLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setLoadError(true);
          setLoading(false);
        }
      });
    return () => { isMounted = false; };
  }, [refreshNonce]);

  const requestRefresh = () => {
    setLoading(true);
    setLoadError(false);
    setRefreshNonce((value) => value + 1);
  };

  const summaryCards = useMemo(() => {
    const activeCount = tools.filter((tool) => tool.is_active !== false).length;
    const categoryCount = new Set(tools.map((tool) => tool.category)).size;
    const parameterizedCount = tools.filter((tool) => Object.keys(tool.parameters ?? {}).length > 0).length;
    return [
      { label: "등록 도구", value: tools.length.toLocaleString(), detail: "워크스페이스 실행 대상", icon: Wrench },
      { label: "활성 도구", value: activeCount.toLocaleString(), detail: "즉시 실행 가능", icon: Power },
      { label: "카테고리", value: categoryCount.toLocaleString(), detail: "운영 분류 기준", icon: SlidersHorizontal },
      { label: "파라미터 계약", value: parameterizedCount.toLocaleString(), detail: "입력 스키마 보유", icon: CheckCircle2 },
    ];
  }, [tools]);

  const handleExecute = async (code: string) => {
    setExecuting(prev => ({ ...prev, [code]: true }));
    try {
      const tool = tools.find((item) => item.code === code);
      const params = parameterValues[code] ?? (tool ? buildDefaultParameters(tool) : {});
      const response = await apiClient.post<ExecuteResponse>(`/api/tools/${code}/execute`, { parameters: params });
      setResults(prev => ({ ...prev, [code]: response }));
    } catch (error: unknown) {
      const err = error as { message?: string };
      setResults(prev => ({
        ...prev,
        [code]: { status: "failed", result: null, message: err.message || "실행 중 오류가 발생했습니다." }
      }));
    } finally {
      setExecuting(prev => ({ ...prev, [code]: false }));
    }
  };

  const toolParametersAreValid = (tool: ToolInfo) => {
    const values = parameterValues[tool.code] ?? buildDefaultParameters(tool);
    return Object.entries(tool.parameters ?? {}).every(([key, descriptor]) => {
      const isOptional = parameterIsOptional(descriptor);
      return (!(key in values) && isOptional) || parameterValueMatchesType(values[key], descriptor);
    });
  };

  const updateParameter = (toolCode: string, key: string, value: unknown) => {
    setParameterValues((currentValues) => ({
      ...currentValues,
      [toolCode]: { ...currentValues[toolCode], [key]: value },
    }));
  };

  return (
    <div className="h-full min-h-0 overflow-y-auto bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 pb-[calc(6rem+env(safe-area-inset-bottom))] md:p-6">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
          <div className="min-w-0">
            <Badge variant="outline" className="gap-1 border-primary/20 bg-primary/10 font-black text-primary">
              <Wrench className="size-3" aria-hidden="true" />
              Tool Registry
            </Badge>
            <h1 className="mt-3 flex items-center gap-3 text-2xl font-black md:text-3xl">
              <Wrench className="size-7 text-primary" aria-hidden="true" />
              도구 실행 콘솔
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              자동화 분석과 작업 실행에 연결된 도구의 상태, 입력 계약, 실행 결과를 확인합니다.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={requestRefresh}
            disabled={loading}
            aria-busy={loading}
            className="font-black"
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} aria-hidden="true" />
            {loading ? "새로고침 중" : "새로고침"}
          </Button>
        </header>

        {!loading && !loadError && tools.length > 0 && (
          <section aria-label="도구 레지스트리 종합" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {summaryCards.map(({ label, value, detail, icon: Icon }) => (
              <Card key={label} size="sm">
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <CardDescription className="font-black">{label}</CardDescription>
                    <Icon className="size-4 text-primary" aria-hidden="true" />
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-black">{value}</p>
                  <p className="mt-1 text-xs font-semibold text-muted-foreground">{detail}</p>
                </CardContent>
              </Card>
            ))}
          </section>
        )}

        {loading ? (
          <Card role="status" aria-live="polite">
            <CardContent className="flex items-center gap-3 py-6 font-bold text-primary">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              도구 목록을 불러오는 중입니다.
            </CardContent>
          </Card>
        ) : loadError ? (
          <Card role="alert" className="border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/15 dark:text-red-200">
            <CardContent className="flex flex-wrap items-center justify-between gap-3 py-5">
              <div className="flex min-w-0 items-center gap-3">
                <AlertCircle className="size-5 shrink-0" aria-hidden="true" />
                <p className="font-black">도구 목록을 불러오지 못했습니다. 잠시 후 다시 시도하세요.</p>
              </div>
              <Button type="button" variant="destructive" onClick={requestRefresh} className="font-black">
                <RefreshCw className="size-4" aria-hidden="true" />
                다시 시도
              </Button>
            </CardContent>
          </Card>
        ) : tools.length === 0 ? (
          <Card role="status" aria-live="polite" className="border-dashed text-center">
            <CardContent className="py-10">
              <Wrench className="mx-auto size-8 text-muted-foreground" aria-hidden="true" />
              <p className="mt-3 font-black">사용 가능한 도구가 없습니다.</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">백엔드 도구 레지스트리가 비어 있으면 이 화면은 실행 버튼을 표시하지 않습니다.</p>
            </CardContent>
          </Card>
        ) : (
          <section aria-label="도구 실행 카드" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {tools.map((tool) => (
              <Card key={tool.code} className={cn(tool.is_active === false && "opacity-70")}>
                <CardHeader>
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="font-black">{tool.category}</Badge>
                        <Badge
                          variant={tool.is_active === false ? "secondary" : "default"}
                          className="font-black"
                        >
                          {tool.is_active === false ? "비활성" : "활성"}
                        </Badge>
                      </div>
                      <CardTitle className="mt-3 font-black">{tool.name}</CardTitle>
                      <CardDescription className="mt-2 leading-6">{tool.description}</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="grid flex-1 gap-4">
                  <div className="rounded-xl border border-border bg-background p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-black text-muted-foreground">입력 파라미터</p>
                      <Badge variant="secondary" className="font-black">
                        {Object.keys(tool.parameters ?? {}).length}
                      </Badge>
                    </div>
                    {Object.keys(tool.parameters ?? {}).length === 0 ? (
                      <p className="mt-2 text-sm font-semibold text-muted-foreground">필요한 입력 없음</p>
                    ) : (
                      <dl className="mt-3 grid gap-2">
                        {Object.entries(tool.parameters ?? {}).map(([key, descriptor]) => {
                          const type = parameterType(descriptor);
                          const inputId = `tool-${tool.code}-${key}`;
                          const inputHelpId = `${inputId}-help`;
                          const value = parameterValues[tool.code]?.[key] ?? defaultParameterValue(descriptor);
                          const inputValue = parameterInputValue(value, type);
                          const isValid = parameterValueMatchesType(value, descriptor);
                          const maxLength = type === "string" ? parameterMaxLength(descriptor) : undefined;
                          return (
                            <div key={key} className="grid gap-2 text-sm">
                              <div className="flex items-center justify-between gap-3">
                                <dt className="min-w-0 truncate font-bold">
                                  <label htmlFor={inputId}>{key}</label>
                                </dt>
                                <dd className="shrink-0 rounded-lg bg-secondary px-2 py-1 text-xs font-black text-muted-foreground">
                                  {parameterTypeLabel(descriptor)}
                                </dd>
                              </div>
                              {type === "boolean" ? (
                                <input
                                  id={inputId}
                                  type="checkbox"
                                  checked={Boolean(inputValue)}
                                  onChange={(event) => updateParameter(tool.code, key, event.target.checked)}
                                  data-tool-parameter={`${tool.code}.${key}`}
                                  className="size-4 accent-primary"
                                />
                              ) : type === "string" ? (
                                <Textarea
                                  id={inputId}
                                  value={String(inputValue)}
                                  maxLength={maxLength}
                                  onChange={(event) => updateParameter(tool.code, key, event.target.value)}
                                  data-tool-parameter={`${tool.code}.${key}`}
                                  aria-label={key}
                                  aria-describedby={maxLength === undefined ? undefined : inputHelpId}
                                  rows={3}
                                />
                              ) : (
                                <Input
                                  id={inputId}
                                  type={type === "number" || type === "integer" ? "number" : "text"}
                                  value={String(inputValue)}
                                  step={type === "integer" ? 1 : undefined}
                                  onChange={(event) => updateParameter(
                                    tool.code,
                                    key,
                                    parameterValueFromInput(event.target.value, type),
                                  )}
                                  data-tool-parameter={`${tool.code}.${key}`}
                                  aria-label={key}
                                  aria-invalid={!isValid}
                                />
                              )}
                              {maxLength !== undefined && (
                                <p id={inputHelpId} className="text-xs font-semibold text-muted-foreground">
                                  최대 {maxLength.toLocaleString()}자
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </dl>
                    )}
                  </div>
                  {results[tool.code] && (
                    <div
                      role="status"
                      aria-live="polite"
                      className={cn("rounded-xl border p-3 text-sm", resultTone(results[tool.code].status))}
                    >
                      <div className="flex items-center gap-2 font-black">
                        {results[tool.code].status === "success" ? (
                          <CheckCircle2 className="size-4" aria-hidden="true" />
                        ) : (
                          <AlertCircle className="size-4" aria-hidden="true" />
                        )}
                        {resultLabel(results[tool.code].status)}
                      </div>
                      <p className="mt-2 break-words text-xs font-semibold leading-5">{resultMessage(results[tool.code])}</p>
                    </div>
                  )}
                </CardContent>
                <CardFooter className="justify-end">
                  <Button
                    type="button"
                    onClick={() => handleExecute(tool.code)}
                    disabled={
                      executing[tool.code] ||
                      tool.is_active === false ||
                      !toolParametersAreValid(tool)
                    }
                    data-tool-execute={tool.code}
                    className="w-full font-black"
                  >
                    {executing[tool.code] ? (
                      <>
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        실행 중
                      </>
                    ) : (
                      <>
                        <Play className="size-4" aria-hidden="true" />
                        {tool.is_active === false ? "비활성 도구" : "실행 테스트"}
                      </>
                    )}
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
