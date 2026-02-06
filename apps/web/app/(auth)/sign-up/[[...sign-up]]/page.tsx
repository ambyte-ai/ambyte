import { SignUp } from "@clerk/nextjs";

export default function Page() {
	return (
		<div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-zinc-950">
			{/* Animated gradient background */}
			<div className="absolute inset-0 bg-gradient-to-br from-zinc-900 via-zinc-950 to-zinc-900" />

			{/* Subtle grid pattern */}
			<div
				className="absolute inset-0 opacity-[0.03]"
				style={{
					backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
				}}
			/>

			{/* Glow effects */}
			<div className="absolute top-1/4 right-1/4 h-96 w-96 rounded-full bg-violet-500/10 blur-3xl" />
			<div className="absolute bottom-1/4 left-1/4 h-96 w-96 rounded-full bg-indigo-500/10 blur-3xl" />

			{/* Content container */}
			<div className="relative z-10 flex flex-col items-center gap-8 px-4 py-8">
				{/* Logo/Brand area */}
				<div className="flex flex-col items-center gap-3">
					<div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 shadow-lg shadow-violet-500/20">
						<svg
							className="h-7 w-7 text-white"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
							/>
						</svg>
					</div>
					<h1 className="text-2xl font-semibold tracking-tight text-white">
						Create an account
					</h1>
					<p className="text-sm text-zinc-400">
						Get started with your free account today
					</p>
				</div>

				{/* Clerk SignUp component with custom appearance */}
				<div className="w-full max-w-md rounded-2xl border border-zinc-800/50 bg-zinc-900/50 p-1 shadow-2xl shadow-black/50 backdrop-blur-xl">
					<SignUp
						appearance={{
							elements: {
								rootBox: "w-full",
								card: "bg-transparent shadow-none border-0 w-full",
								headerTitle: "hidden",
								headerSubtitle: "hidden",
								socialButtonsBlockButton:
									"bg-zinc-800 border-zinc-700 text-white hover:bg-zinc-700 transition-colors",
								socialButtonsBlockButtonText: "text-white font-medium",
								dividerLine: "bg-zinc-700",
								dividerText: "text-zinc-500",
								formFieldLabel: "text-zinc-300",
								formFieldInput:
									"bg-zinc-800 border-zinc-700 text-white placeholder:text-zinc-500 focus:border-violet-500 focus:ring-violet-500/20",
								formButtonPrimary:
									"bg-gradient-to-r from-violet-500 to-indigo-600 hover:from-violet-600 hover:to-indigo-700 text-white shadow-lg shadow-violet-500/25 transition-all duration-200",
								footerActionLink: "text-violet-400 hover:text-violet-300",
								identityPreviewText: "text-zinc-300",
								identityPreviewEditButton:
									"text-violet-400 hover:text-violet-300",
								formFieldAction: "text-violet-400 hover:text-violet-300",
								alertText: "text-zinc-300",
								formFieldInputShowPasswordButton:
									"text-zinc-400 hover:text-zinc-300",
							},
							layout: {
								socialButtonsPlacement: "top",
								socialButtonsVariant: "blockButton",
							},
						}}
					/>
				</div>

				{/* Features highlight */}
				<div className="flex flex-wrap items-center justify-center gap-6 text-xs text-zinc-500">
					<div className="flex items-center gap-2">
						<svg
							className="h-4 w-4 text-emerald-500"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								d="M5 13l4 4L19 7"
							/>
						</svg>
						<span>Free forever</span>
					</div>
					<div className="flex items-center gap-2">
						<svg
							className="h-4 w-4 text-emerald-500"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								d="M5 13l4 4L19 7"
							/>
						</svg>
						<span>No credit card required</span>
					</div>
					<div className="flex items-center gap-2">
						<svg
							className="h-4 w-4 text-emerald-500"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								d="M5 13l4 4L19 7"
							/>
						</svg>
						<span>Cancel anytime</span>
					</div>
				</div>
			</div>
		</div>
	);
}
