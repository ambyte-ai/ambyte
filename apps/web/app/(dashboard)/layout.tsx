import { Header } from "@/components/layout/header";
import { Sidebar } from "@/components/layout/sidebar";
import { ProjectProvider } from "@/context/project-context";

export default function DashboardLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return (
		<ProjectProvider>
			<div className="flex min-h-screen bg-background text-foreground">
				{/* Fixed Sidebar */}
				<aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-border bg-card">
					<Sidebar />
				</aside>

				{/* Main Content Area */}
				<main className="flex-1 pl-64 transition-all duration-300 ease-in-out">
					<Header />

					{/* The Bento Grid Container */}
					<div className="container mx-auto p-6 max-w-7xl">{children}</div>
				</main>
			</div>
		</ProjectProvider>
	);
}
