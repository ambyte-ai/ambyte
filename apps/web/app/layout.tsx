import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import "./global.css";

export default function RootLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return (
		<ClerkProvider
			afterSignOutUrl="/sign-in"
			appearance={{
				baseTheme: dark,
				variables: { colorPrimary: "#0ea5e9" }, // Cyan-500 (Ambyte Brand)
			}}
		>
			<html lang="en" className="dark">
				<body className="bg-background text-foreground min-h-screen">
					{children}
				</body>
			</html>
		</ClerkProvider>
	);
}
