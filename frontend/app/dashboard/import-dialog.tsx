"use client";

import { AlertTriangle, CheckCircle2, FileJson2, FileSpreadsheet, Upload, X } from "lucide-react";
import { useMemo, useState } from "react";

type ImportFormat = "csv" | "json";

type ImportPreview = {
  can_import: boolean;
  detected_columns?: string[];
  suggested_mapping?: Record<string, string>;
  missing_required_fields?: string[];
  errors?: string[];
  sample_rows: Record<string, unknown>[];
  total_rows?: number;
  request_ids?: string[];
};

type ImportConfirmation = {
  imported: number;
  request_ids: string[];
};

type ImportDialogProps = {
  apiBase: string;
  onClose: () => void;
  onImported: (message: string) => Promise<void>;
};

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function errorMessages(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") {
    return [fallback];
  }

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return [detail];
  }
  if (!Array.isArray(detail)) {
    return [fallback];
  }

  return detail.map((item) => {
    if (typeof item === "string") {
      return item;
    }
    if (item && typeof item === "object") {
      const validation = item as { loc?: unknown[]; msg?: string };
      const location = Array.isArray(validation.loc)
        ? validation.loc.filter((part) => part !== "body" && part !== "file").join(".")
        : "";
      return `${location ? `${location}: ` : ""}${validation.msg ?? JSON.stringify(item)}`;
    }
    return String(item);
  });
}

async function responsePayload(response: Response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { detail: text };
  }
}

export default function ImportDialog({ apiBase, onClose, onImported }: ImportDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [completion, setCompletion] = useState("");

  const format = useMemo<ImportFormat | null>(() => {
    if (!file) {
      return null;
    }
    const extension = file.name.split(".").pop()?.toLowerCase();
    return extension === "csv" || extension === "json" ? extension : null;
  }, [file]);

  const sampleColumns = useMemo(() => {
    if (!preview) {
      return [];
    }
    if (preview.detected_columns?.length) {
      return preview.detected_columns;
    }
    return Array.from(new Set(preview.sample_rows.flatMap((row) => Object.keys(row))));
  }, [preview]);

  const busy = isPreviewing || isConfirming;

  function selectFile(nextFile: File | null) {
    setFile(nextFile);
    setPreview(null);
    setErrors([]);
    setCompletion("");
    if (nextFile && !/\.(csv|json)$/i.test(nextFile.name)) {
      setErrors(["Choose a .csv or .json file."]);
    }
  }

  async function upload(endpoint: string) {
    if (!file) {
      throw new Error("Choose a CSV or JSON file first.");
    }
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${apiBase}${endpoint}`, {
      method: "POST",
      body: formData
    });
    const payload = await responsePayload(response);
    if (!response.ok) {
      throw new Error(errorMessages(payload, "The import request failed.").join(" "));
    }
    return payload;
  }

  async function previewFile() {
    if (!file || !format) {
      setErrors(["Choose a .csv or .json file first."]);
      return;
    }

    setIsPreviewing(true);
    setPreview(null);
    setErrors([]);
    setCompletion("");
    try {
      const endpoint = format === "csv" ? "/api/import/preview" : "/api/import/json/preview";
      const payload = (await upload(endpoint)) as ImportPreview;
      setPreview(payload);
      setErrors(payload.errors ?? []);
    } catch (error) {
      setErrors([error instanceof Error ? error.message : "The file could not be previewed."]);
    } finally {
      setIsPreviewing(false);
    }
  }

  async function confirmImport() {
    if (!file || !format || !preview?.can_import) {
      return;
    }

    setIsConfirming(true);
    setErrors([]);
    try {
      const endpoint = format === "csv" ? "/api/import/confirm" : "/api/import/json/confirm";
      const payload = (await upload(endpoint)) as ImportConfirmation;
      const message = `${payload.imported} request${payload.imported === 1 ? "" : "s"} imported: ${payload.request_ids.join(", ")}.`;
      setCompletion(message);
      await onImported(message);
    } catch (error) {
      setErrors([error instanceof Error ? error.message : "The file could not be imported."]);
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <section className="import-dialog" role="dialog" aria-modal="true" aria-labelledby="import-dialog-title">
        <header className="import-dialog-header">
          <div>
            <span className="eyebrow">Data import</span>
            <h2 id="import-dialog-title">Preview CSV or JSON requests</h2>
            <p>No data is stored until you review the preview and confirm.</p>
          </div>
          <button className="icon-button" onClick={onClose} disabled={busy} aria-label="Close import dialog">
            <X size={20} />
          </button>
        </header>

        <div className="import-dialog-body">
          <label className={`file-drop ${file ? "has-file" : ""}`} htmlFor="request-import-file">
            {format === "json" ? <FileJson2 size={28} /> : <FileSpreadsheet size={28} />}
            <strong>{file?.name ?? "Choose a CSV or JSON file"}</strong>
            <span>{file ? `${(file.size / 1024).toFixed(1)} KB selected` : "UTF-8 format, up to 1 MB"}</span>
            <input
              id="request-import-file"
              type="file"
              accept=".csv,.json,text/csv,application/json"
              onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
              disabled={busy}
            />
          </label>

          {errors.length > 0 && (
            <section className="import-notice error" aria-live="polite">
              <AlertTriangle size={18} />
              <div>
                <strong>Fix these issues before importing</strong>
                <ul>
                  {errors.map((error, index) => <li key={`${error}-${index}`}>{error}</li>)}
                </ul>
              </div>
            </section>
          )}

          {completion && (
            <section className="import-notice success" aria-live="polite">
              <CheckCircle2 size={18} />
              <div><strong>Import complete</strong><p>{completion}</p></div>
            </section>
          )}

          {preview && (
            <div className="import-preview">
              <section className="import-summary">
                <div>
                  <span>Format</span>
                  <strong>{format?.toUpperCase()}</strong>
                </div>
                <div>
                  <span>Total rows</span>
                  <strong>{preview.total_rows ?? preview.sample_rows.length}</strong>
                </div>
                <div className={preview.can_import ? "ready" : "blocked"}>
                  <span>Validation</span>
                  <strong>{preview.can_import ? "Ready" : "Blocked"}</strong>
                </div>
              </section>

              {preview.detected_columns && (
                <section className="import-section">
                  <div className="import-section-heading">
                    <h3>Detected columns</h3>
                    <span>{preview.detected_columns.length} found</span>
                  </div>
                  <div className="column-chips">
                    {preview.detected_columns.map((column) => <span key={column}>{column}</span>)}
                  </div>
                </section>
              )}

              {preview.suggested_mapping && Object.keys(preview.suggested_mapping).length > 0 && (
                <section className="import-section">
                  <div className="import-section-heading"><h3>Suggested mapping</h3><span>file → RailFlowAI</span></div>
                  <div className="mapping-grid">
                    {Object.entries(preview.suggested_mapping).map(([external, internal]) => (
                      <div key={external}><span>{external}</span><strong>{internal}</strong></div>
                    ))}
                  </div>
                </section>
              )}

              {(preview.missing_required_fields?.length ?? 0) > 0 && (
                <section className="import-notice error">
                  <AlertTriangle size={18} />
                  <div>
                    <strong>Missing required fields</strong>
                    <p>{preview.missing_required_fields?.join(", ")}</p>
                  </div>
                </section>
              )}

              <section className="import-section">
                <div className="import-section-heading"><h3>Sample rows</h3><span>first five maximum</span></div>
                {preview.sample_rows.length > 0 ? (
                  <div className="import-table-wrap">
                    <table className="import-table">
                      <thead><tr>{sampleColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                      <tbody>
                        {preview.sample_rows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {sampleColumns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="muted">The file contains no data rows.</p>}
              </section>
            </div>
          )}
        </div>

        <footer className="import-dialog-actions">
          <button className="button secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="button secondary" onClick={previewFile} disabled={!file || !format || busy}>
            <Upload size={18} />
            {isPreviewing ? "Checking file..." : preview ? "Preview again" : "Preview file"}
          </button>
          <button className="button" onClick={confirmImport} disabled={!preview?.can_import || busy || Boolean(completion)}>
            <CheckCircle2 size={18} />
            {isConfirming ? "Importing..." : "Confirm import"}
          </button>
        </footer>
      </section>
    </div>
  );
}
