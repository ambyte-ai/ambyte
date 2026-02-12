import {
	Brain,
	Clock,
	Globe,
	HelpCircle,
	type LucideIcon,
	Shield,
	Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Obligation } from "@/types/obligation";

interface ConstraintIconProps {
	obligation: Obligation;
	className?: string;
}

type ConstraintConfig = {
	icon: LucideIcon;
	colorClass: string;
	label: string;
};

export function ConstraintIcon({ obligation, className }: ConstraintIconProps) {
	// Mapping logic to determine which icon to show
	let config: ConstraintConfig | null = null;

	if (obligation.retention) {
		config = {
			icon: Clock,
			colorClass: "text-orange-500",
			label: "Retention Rule",
		};
	} else if (obligation.geofencing) {
		config = {
			icon: Globe,
			colorClass: "text-emerald-500",
			label: "Geofencing Rule",
		};
	} else if (obligation.purpose) {
		config = {
			icon: Target,
			colorClass: "text-blue-500",
			label: "Purpose Restriction",
		};
	} else if (obligation.privacy) {
		config = {
			icon: Shield,
			colorClass: "text-violet-500",
			label: "Privacy Enhancement",
		};
	} else if (obligation.ai_model) {
		config = {
			icon: Brain,
			colorClass: "text-rose-500",
			label: "AI Model Constraint",
		};
	}

	// Fallback if no constraint is found (though ideally one should exist if it's an obligation)
	if (!config) {
		return (
			<HelpCircle
				className={cn("h-4 w-4 text-muted-foreground", className)}
				aria-label="Unknown Constraint"
			/>
		);
	}

	const Icon = config.icon;

	return (
		<div
			className={cn("flex items-center justify-center", className)}
			title={config.label}
		>
			<Icon
				className={cn("h-4 w-4", config.colorClass)}
				aria-label={config.label}
			/>
		</div>
	);
}
