"use client";

import * as React from "react";
import { ArrowRight, CornerDownLeft, HelpCircle, Loader2 } from "lucide-react";
import { clientAdapter, type CaptureTaskResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Natural language capture view module.
 * Establishes an intake interface that connects directly to the backend intake seam.
 * Preserves high locality by handling clarification dialogue inline when required.
 */
interface CaptureBoxProps {
  ownerId: string;
  onCaptured: () => void;
}

export function CaptureBox({ ownerId, onCaptured }: CaptureBoxProps) {
  const [rawText, setRawText] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Clarification state
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

  return (
    <div className="w-full">
      <form onSubmit={handleCapture} className="relative">
        <div className="relative flex items-center">
          <Input
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Capture a commitment or task in plain text..."
            className="h-12 bg-[#140c06] border-surface-cork/80 pr-24 pl-4 text-sm text-cream placeholder:text-cream-muted/60 rounded-xl focus-visible:ring-ember focus-visible:border-ember"
            disabled={isSubmitting}
          />
          <div className="absolute right-2 flex items-center">
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

      {errorMessage && (
        <p className="mt-2 text-xs text-red-400 pl-1">{errorMessage}</p>
      )}

      {/* Clarification Dialog */}
      <Dialog
        open={Boolean(clarificationData)}
        onOpenChange={(open) => {
          if (!open) {
            setClarificationData(null);
            setClarificationText("");
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2 text-ember">
              <HelpCircle className="h-4 w-4" />
              <DialogTitle>Clarification Needed</DialogTitle>
            </div>
            <DialogDescription className="text-xs text-cream-muted">
              Praxis needs a quick clarification to resolve ambiguity before scheduling execution.
            </DialogDescription>
          </DialogHeader>

          <div className="py-2 space-y-3">
            <div className="rounded-lg bg-[#1e130a] p-3 border border-surface-cork/60 text-xs text-cream">
              <span className="text-cream-muted block mb-1 uppercase tracking-wider text-[10px]">
                Original intent:
              </span>
              <p className="italic font-serif text-cream/90">
                &ldquo;{clarificationData?.commitment.raw_text}&rdquo;
              </p>
            </div>

            <div className="rounded-lg bg-[#26160c] p-3 border border-ember/40 text-xs text-cream">
              <span className="text-ember block mb-1 uppercase tracking-wider text-[10px] font-medium">
                Question:
              </span>
              <p className="text-cream font-medium">
                {clarificationData?.clarification_prompt}
              </p>
            </div>

            <form onSubmit={handleClarificationSubmit} className="space-y-3 pt-1">
              <Input
                value={clarificationText}
                onChange={(e) => setClarificationText(e.target.value)}
                placeholder="Type your response..."
                className="bg-[#100904] border-surface-cork text-xs"
                autoFocus
                disabled={isClarifying}
              />

              <DialogFooter className="gap-2 sm:gap-0">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setClarificationData(null)}
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
              </DialogFooter>
            </form>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
