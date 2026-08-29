import { createFileRoute } from "@tanstack/react-router";

import { Experience } from "@/components/Experience";
import { Nav } from "@/components/Nav";
import { ScrollController } from "@/components/ScrollController";
import { StoryOverlay } from "@/components/StoryOverlay";
import { AuthOverlay } from "@/components/auth/AuthOverlay";

export const Route = createFileRoute("/")({
  ssr: false,
  component: Index,
});

function Index() {
  return (
    <>
      <ScrollController />
      <div id="top" />
      <main id="story" className="relative w-full bg-background">
        <div id="stage" className="relative h-screen w-full overflow-hidden">
          <Experience />
          <div className="stage-vignette" />
          <Nav />
          <StoryOverlay />
        </div>
        <div className="h-[2000vh]" aria-hidden="true" />
        <h1 className="sr-only">
          Argus — blockchain intelligence as an interactive 3D experience
        </h1>
      </main>
      <AuthOverlay />
    </>
  );
}
