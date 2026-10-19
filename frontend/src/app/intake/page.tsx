"use client";
import { PageHeader } from "@/components/shell/AppShell";
import { IntakeFlow } from "@/components/intake/Intake";

export default function IntakePage() {
  return (
    <div>
      <PageHeader
        title="Add patient"
        sub="Upload a recording or start a new patient. Data are validated, clarified and run through the same twin as the research replay — as a separate DEVELOPMENT session."
      />
      <div className="p-6">
        <IntakeFlow />
      </div>
    </div>
  );
}
