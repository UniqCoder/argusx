import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL =
  (import.meta.env["VITE_SUPABASE_URL"] as string | undefined) ??
  "https://vmhuinslcaesqlpeuqsm.supabase.co";
const SUPABASE_ANON_KEY =
  (import.meta.env["VITE_SUPABASE_ANON_KEY"] as string | undefined) ??
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZtaHVpbnNsY2Flc3FscGV1cXNtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5MzUyMDYsImV4cCI6MjEwMzUxMTIwNn0.E-ppummwyiuBmpn0Z_YyEAt0fbkkNJbI-3RA224nD3Y";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
