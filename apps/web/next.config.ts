import type { NextConfig } from "next";
import fs from "fs";
import path from "path";

let appVersion = "v0.1.0-alpha";
try {
	const pyprojectPath = path.join(process.cwd(), "../../packages/ambyte/pyproject.toml");
	const pyprojectContent = fs.readFileSync(pyprojectPath, "utf-8");
	const match = pyprojectContent.match(/^version\s*=\s*"([^"]+)"/m);
	if (match && match[1]) {
		appVersion = `v${match[1]}`;
	}
} catch (e) {
	console.error("Failed to read pyproject.toml version", e);
}

const nextConfig: NextConfig = {
	output: "standalone",
	env: {
		NEXT_PUBLIC_APP_VERSION: appVersion,
	},
};

export default nextConfig;
