"use client";

import * as React from "react";
import { ArrowRight, CornerDownLeft, HelpCircle, Loader2, Sparkles } from "lucide-react";
import { clientAdapter, type CaptureTaskResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Natural language capture intake module.
 * Establishes an intake interface that connects directly to the backend intake seam.
 * Preserves high locality by handling clarification dialogue inline when required,
 * allowing users to leverage natural language with maximum operational depth.
 */
interface CaptureBoxProps {
  ownerId: string;
  onCaptured: () => void;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}

const SYNTAX_HINTS = [
  { label: "#urgent", text: " #urgent" },
  { label: "#important", text: " #important" },
  { label: "by tomorrow 5pm", text: " by tomorrow 5pm" },
  { label: "tool:webhook", text: " tool:webhook" },
];

export function CaptureBox({ ownerId, onCaptured, inputRef: externalRef }: CaptureBoxProps) {
  const [rawText, setRawText] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const internalRef = React.useRef<HTMLInputElement | null>(null);
  const effectiveRef = externalRef || internalRef;

  // Clarification state handled inline to preserve locality
  const [clarificationData, setClarificationData] = React.useState<CaptureTaskResponse | null>(null);
  const [clarificationText, setClarificationText] = React.useState("");
  const [isClarifying, setIsClarifying] = React.useState(false);

  async function handleCapture(event: React.FormEvent) {
    event.preventDefault();
    if (!rawText.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await clientAdapter.captureTask({
        ownerId,
        rawText: rawText.trim(),
      });

      if (response.clarification_needed && response.clarification_prompt) {
        setClarificationData(response);
      } else {
        setRawText("");
        setClarificationData(null);
        onCaptured();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to capture commitment";
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleClarificationSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!clarificationData || !clarificationText.trim() || isClarifying) return;

    setIsClarifying(true);
    try {
      const result = await clientAdapter.clarifyCommitment({
        commitmentId: clarificationData.commitment.id,
        ownerId,
        clarificationResponse: clarificationText.trim(),
      });

      if (result.clarification_needed && result.clarification_prompt) {
        setClarificationData(result);
        setClarificationText("");
      } else {
        setClarificationData(null);
        setClarificationText("");
        setRawText("");
        onCaptured();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to clarify commitment";
      setErrorMessage(msg);
    } finally {
      setIsClarifying(false);
    }
  }

  function handleAppendHint(textToAppend: string) {
    setRawText((prev) => `${prev.trimEnd()}${textToAppend}`);
    effectiveRef.current?.focus();
  }

  return (
    <div className="w-full space-y-2">
      <form onSubmit={handleCapture} className="relative">
        <div className="relative flex items-center">
          <Input
            ref={effectiveRef}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Capture a commitment or task in plain text... (Press / to focus)"
            className="h-12 bg-[#140c06] border-surface-cork/80 pr-28 pl-4 text-sm text-cream placeholder:text-cream-muted/60 rounded-xl focus-visible:ring-1 focus-visible:ring-cream/40 focus-visible:border-cream/40"
            disabled={isSubmitting}
          />
          <div className="absolute right-2 flex items-center gap-1.5">
            <Button
              type="submit"
              disabled={isSubmitting || !rawText.trim()}
              size="sm"
              className="h-8 px-3 rounded-lg bg-surface-bark hover:bg-[#4a301e] text-cream border border-surface-cork"
            >
              {isSubmitting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <>
                  <span className="hidden sm:inline mr-1 text-[11px]">Capture</span>
                  <CornerDownLeft className="h-3 w-3" />
                </>
              )}
            </Button>
          </div>
        </div>
      </form>

      {/* Syntax input hints row */}
      <div className="flex flex-wrap items-center gap-1.5 px-1 text-[10px] text-cream-muted">
        <span className="uppercase tracking-wider mr-1">Hints:</span>
        {SYNTAX_HINTS.map((hint) => (
          <button
            key={hint.label}
            type="button"
            onClick={() => handleAppendHint(hint.text)}
            className="px-2 py-0.5 rounded-full border border-surface-cork/60 bg-[#140c06] hover:border-surface-cork hover:text-cream text-cream-muted transition-colors font-mono"
            title={`Insert '${hint.label}' into capture prompt`}
          >
            {hint.label}
          </button>
        ))}
      </div>

      {errorMessage && (
        <p className="mt-2 text-xs text-red-400 pl-1">{errorMessage}</p>
      )}

      {/* Inline Clarification Drawer (Locality Preservation) */}
      {clarificationData && (
        <div className="p-4 rounded-xl border border-surface-cork bg-[#160d07] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-ember">
              <HelpCircle className="h-4 w-4" />
              <span className="text-xs uppercase font-medium tracking-wider text-cream">
                Clarification Needed
              </span>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setClarificationData(null);
                setClarificationText("");
              }}
              disabled={isClarifying}
              className="h-6 px-2 text-[10px] text-cream-muted hover:text-cream"
            >
              Dismiss
            </Button>
          </div>

          <p className="text-xs text-cream-muted">
            Praxis needs a quick clarification to resolve ambiguity before scheduling execution.
          </p>

          <div className="rounded-lg bg-[#110904] p-3 border border-surface-cork/60 text-xs text-cream">
            <span className="text-cream-muted block mb-1 uppercase tracking-wider text-[10px]">
              Original intent:
            </span>
            <p className="italic font-serif text-cream/90">
              &ldquo;{clarificationData.commitment.raw_text}&rdquo;
            </p>
          </div>

          <div className="rounded-lg bg-[#221006] p-3 border border-ember/40 text-xs text-cream">
            <span className="text-ember block mb-1 uppercase tracking-wider text-[10px] font-medium">
              Question:
            </span>
            <p className="text-cream font-medium">
              {clarificationData.clarification_prompt}
            </p>
          </div>

          <form onSubmit={handleClarificationSubmit} className="space-y-3 pt-1">
            <Input
              value={clarificationText}
              onChange={(e) => setClarificationText(e.target.value)}
              placeholder="Type your clarification response..."
              className="bg-[#100904] border-surface-cork text-xs"
              autoFocus
              disabled={isClarifying}
            />

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setClarificationData(null);
                  setClarificationText("");
                }}
                disabled={isClarifying}
              >
                Skip for Now
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={isClarifying || !clarificationText.trim()}
                className="bg-surface-bark text-cream border border-surface-cork hover:bg-[#4a301e]"
              >
                {isClarifying ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <ArrowRight className="h-3 w-3 mr-1" />
                )}
                Save Clarification
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
