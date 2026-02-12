import type { Obligation } from "@/types/obligation";
import { AiModelVisualizer } from "./visualizers/ai-model-visualizer";
import { GeofencingVisualizer } from "./visualizers/geofencing-visualizer";
import { PrivacyVisualizer } from "./visualizers/privacy-visualizer";
import { PurposeVisualizer } from "./visualizers/purpose-visualizer";
import { RetentionVisualizer } from "./visualizers/retention-visualizer";

interface ConstraintVisualizerProps {
	obligation: Obligation;
}

export function ConstraintVisualizer({
	obligation,
}: ConstraintVisualizerProps) {
	if (obligation.retention) {
		return <RetentionVisualizer rule={obligation.retention} />;
	}

	if (obligation.geofencing) {
		return <GeofencingVisualizer rule={obligation.geofencing} />;
	}

	if (obligation.purpose) {
		return <PurposeVisualizer rule={obligation.purpose} />;
	}

	if (obligation.privacy) {
		return <PrivacyVisualizer rule={obligation.privacy} />;
	}

	if (obligation.ai_model) {
		return <AiModelVisualizer rule={obligation.ai_model} />;
	}

	return (
		<div className="text-sm text-muted-foreground italic">
			No specific constraints defined.
		</div>
	);
}
