import {
	BookOpen,
	Code2,
	ExternalLink,
	FileText,
	ShieldCheck,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Obligation } from "@/types/obligation";
import { ConstraintVisualizer } from "./constraint-visualizer";
import { EnforcementBadge } from "./enforcement-badge";
import { ScopeVisualizer } from "./scope-visualizer";

interface ObligationDrawerProps {
	obligation: Obligation | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

function getDocumentUrl(uri?: string) {
	if (!uri) return "#";

	// If it's already an HTTP link, just return it
	if (uri.startsWith("http://") || uri.startsWith("https://")) {
		return uri;
	}

	// Convert s3://bucket/key to local MinIO HTTP URL
	if (uri.startsWith("s3://")) {
		const path = uri.replace("s3://", "");
		// Port 9000 is where MinIO serves files
		return `http://localhost:9000/${path}`;
	}

	return uri;
}

export function ObligationDrawer({
	obligation,
	open,
	onOpenChange,
}: ObligationDrawerProps) {
	if (!obligation) return null;

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent className="w-[500px] sm:w-[600px] sm:max-w-none p-0 flex flex-col">
				{/* Header */}
				<div className="p-6 pb-2">
					<SheetHeader className="mb-4 space-y-4">
						<div className="flex items-start justify-between gap-4">
							<div className="space-y-1">
								<SheetTitle className="text-xl font-bold leading-tight">
									{obligation.title}
								</SheetTitle>
								<div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
									<span>{obligation.id}</span>
								</div>
							</div>
							<EnforcementBadge level={obligation.enforcement_level} />
						</div>
						<SheetDescription className="text-sm text-foreground/80 leading-relaxed">
							{obligation.description}
						</SheetDescription>
					</SheetHeader>
					<Separator />
				</div>

				{/* Content */}
				<div className="flex-1 overflow-hidden">
					<Tabs defaultValue="definition" className="h-full flex flex-col">
						<div className="px-6">
							<TabsList className="w-full justify-start rounded-none border-b bg-transparent p-0 h-auto">
								<TabsTrigger
									value="definition"
									className="relative h-9 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground data-[state=active]:shadow-none"
								>
									<ShieldCheck className="mr-2 h-4 w-4" />
									Definition
								</TabsTrigger>
								<TabsTrigger
									value="scope"
									className="relative h-9 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground data-[state=active]:shadow-none"
								>
									<FilterIcon className="mr-2 h-4 w-4" />
									Scope
								</TabsTrigger>
								<TabsTrigger
									value="provenance"
									className="relative h-9 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground data-[state=active]:shadow-none"
								>
									<BookOpen className="mr-2 h-4 w-4" />
									Provenance
								</TabsTrigger>
								<TabsTrigger
									value="code"
									className="relative h-9 rounded-none border-b-2 border-transparent bg-transparent px-4 pb-3 pt-2 font-semibold text-muted-foreground shadow-none transition-none data-[state=active]:border-primary data-[state=active]:text-foreground data-[state=active]:shadow-none"
								>
									<Code2 className="mr-2 h-4 w-4" />
									Code
								</TabsTrigger>
							</TabsList>
						</div>

						<ScrollArea className="flex-1 p-6">
							<TabsContent
								value="definition"
								className="mt-0 space-y-6 focus-visible:outline-none"
							>
								<div className="space-y-4">
									<h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
										Constraint Logic
									</h3>
									<ConstraintVisualizer obligation={obligation} />
								</div>
							</TabsContent>

							<TabsContent
								value="scope"
								className="mt-0 focus-visible:outline-none"
							>
								<div className="space-y-4">
									<h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
										Applicability Scope
									</h3>
									<ScopeVisualizer selector={obligation.target} />
								</div>
							</TabsContent>

							<TabsContent
								value="provenance"
								className="mt-0 focus-visible:outline-none"
							>
								<div className="space-y-6">
									<div className="space-y-4">
										<h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
											Source Details
										</h3>
										<div className="grid gap-4 rounded-lg border bg-card p-4">
											<div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
												<div className="space-y-1">
													<span className="text-xs font-medium text-muted-foreground">
														Source ID
													</span>
													<p className="font-mono text-sm font-medium">
														{obligation.provenance.source_id}
													</p>
												</div>
												<div className="space-y-1">
													<span className="text-xs font-medium text-muted-foreground">
														Document Type
													</span>
													<p className="font-mono text-sm font-medium">
														{obligation.provenance.document_type}
													</p>
												</div>
											</div>

											{obligation.provenance.section_reference && (
												<div className="space-y-1 pt-2 border-t">
													<span className="text-xs font-medium text-muted-foreground">
														Section / Reference
													</span>
													<p className="text-sm italic text-muted-foreground">
														"{obligation.provenance.section_reference}"
													</p>
												</div>
											)}
										</div>
									</div>

									{obligation.provenance.document_uri && (
										<div className="space-y-2">
											<h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
												Resources
											</h3>
											<a
												href={getDocumentUrl(
													obligation.provenance.document_uri,
												)}
												target="_blank"
												rel="noopener noreferrer"
												className="flex items-center gap-2 text-sm text-primary hover:underline bg-muted/30 p-3 rounded-md border"
											>
												<FileText className="h-4 w-4" />
												Original Document
												<ExternalLink className="h-3 w-3 ml-auto opacity-50" />
											</a>
										</div>
									)}
								</div>
							</TabsContent>

							<TabsContent
								value="code"
								className="mt-0 focus-visible:outline-none"
							>
								<div className="rounded-lg border bg-muted/30 p-4 font-mono text-xs overflow-x-auto">
									<pre>{JSON.stringify(obligation, null, 2)}</pre>
								</div>
							</TabsContent>
						</ScrollArea>
					</Tabs>
				</div>
			</SheetContent>
		</Sheet>
	);
}

// Helper icon
function FilterIcon(props: React.SVGProps<SVGSVGElement>) {
	return (
		<svg
			{...props}
			xmlns="http://www.w3.org/2000/svg"
			width="24"
			height="24"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
		>
			<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
		</svg>
	);
}
