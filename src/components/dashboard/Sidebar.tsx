import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import { useSessionStore } from "@/store/session-store";

type NavItem = {
  label: string;
  to: string;
  icon: React.ReactNode;
};

type NavSection = {
  heading: string;
  items: NavItem[];
};

function Icon({ path, filled }: { path: string; filled?: boolean }) {
  return (
    <svg
      className="ug-nav-item__icon"
      viewBox="0 0 16 16"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={path} />
    </svg>
  );
}

const NAV_SECTIONS: NavSection[] = [
  {
    heading: "Overview",
    items: [
      {
        label: "Command Center",
        to: "/dashboard",
        icon: (
          <Icon path="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 11a3 3 0 100-6 3 3 0 000 6z" />
        ),
      },
    ],
  },
  {
    heading: "Investigate",
    items: [
      {
        label: "Trace Wallet",
        to: "/dashboard/trace",
        icon: <Icon path="M8 2v12M2 8h12M5 5l6 6M11 5l-6 6" />,
      },
      {
        label: "Cases",
        to: "/dashboard/cases",
        icon: (
          <Icon path="M3 3h10a1 1 0 011 1v9a1 1 0 01-1 1H3a1 1 0 01-1-1V4a1 1 0 011-1zM5 7h6M5 10h4" />
        ),
      },
    ],
  },
  {
    heading: "Intelligence",
    items: [
      {
        label: "Cross-Victim",
        to: "/dashboard/cross-victim",
        icon: (
          <Icon path="M4 4a2 2 0 100 4 2 2 0 000-4zM12 4a2 2 0 100 4 2 2 0 000-4zM8 10a2 2 0 100 4 2 2 0 000-4zM5.8 6.5L8 9M10.2 6.5L8 9" />
        ),
      },
      {
        label: "Network Signals",
        to: "/dashboard/signals",
        icon: (
          <Icon path="M8 8m-2 0a2 2 0 104 0 2 2 0 10-4 0M8 8m-5 0a5 5 0 1010 0 5 5 0 10-10 0M1 8h2M13 8h2M8 1v2M8 13v2" />
        ),
      },
      {
        label: "Risk Intelligence",
        to: "/dashboard/risk",
        icon: (
          <Icon path="M8 2l1.5 3.5H13l-2.8 2.1 1 3.4L8 9.2l-3.2 1.8 1-3.4L3 5.5h3.5z" />
        ),
      },
    ],
  },
  {
    heading: "Operations",
    items: [
      {
        label: "Live Alerts",
        to: "/dashboard/alerts",
        icon: (
          <Icon path="M8 2a4.5 4.5 0 00-4.5 4.5v3L2 11h12l-1.5-1.5v-3A4.5 4.5 0 008 2zM6.5 11.5a1.5 1.5 0 003 0" />
        ),
      },
      {
        label: "Deposit Watch",
        to: "/dashboard/deposit",
        icon: <Icon path="M8 2v6l3 3M2 8a6 6 0 1012 0A6 6 0 002 8z" />,
      },
    ],
  },
  {
    heading: "Evidence",
    items: [
      {
        label: "Evidence Trail",
        to: "/dashboard/evidence",
        icon: <Icon path="M4 3h8M4 7h8M4 11h5M10 12l2 2 3-3" />,
      },
      {
        label: "Reports",
        to: "/dashboard/reports",
        icon: (
          <Icon path="M3 2h10a1 1 0 011 1v11l-3-2-2 2-2-2-3 2V3a1 1 0 011-1z" />
        ),
      },
    ],
  },
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const logout = useSessionStore((s) => s.logout);

  const isActive = (to: string) => {
    if (to === "/dashboard") return path === "/dashboard";
    return path.startsWith(to);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      navigate({ to: "/" });
    }
  };

  return (
    <aside className="ug-sidebar">
      {/* Brand */}
      <Link to="/dashboard" className="ug-sidebar__brand">
        <span className="ug-sidebar__mark" />
        <span className="ug-sidebar__wordmark">Argus</span>
      </Link>

      <div className="ug-sidebar__tagline">Real-Time Intelligence</div>

      <nav style={{ flex: 1, paddingBottom: "0.5rem" }}>
        {NAV_SECTIONS.map((section) => (
          <div key={section.heading} className="ug-sidebar__section">
            <p className="ug-sidebar__section-label">{section.heading}</p>
            {section.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={`ug-nav-item${isActive(item.to) ? " is-active" : ""}`}
              >
                {item.icon}
                {item.label}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <div className="ug-sidebar__bottom">
        <Link to="/dashboard/settings" className="ug-nav-item">
          <Icon path="M8 10a2 2 0 100-4 2 2 0 000 4zM8 2v1.5M8 12.5V14M2 8H3.5M12.5 8H14M3.8 3.8l1.1 1.1M11.1 11.1l1.1 1.1M3.8 12.2l1.1-1.1M11.1 4.9l1.1-1.1" />
          Settings
        </Link>
        <button
          type="button"
          className="ug-nav-item"
          style={{ gap: "0.6rem" }}
          onClick={handleLogout}
          aria-label="Sign out"
        >
          <Icon path="M10 8H3M6 5l-3 3 3 3M13 4v8" />
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.1rem",
              textAlign: "left",
              flex: 1,
            }}
          >
            <span
              style={{
                fontSize: "0.76rem",
                fontWeight: 600,
                color: "var(--color-foreground)",
                fontFamily: "var(--font-display)",
              }}
            >
              Sign out
            </span>
            <span
              style={{
                fontSize: "0.6rem",
                fontFamily: "var(--font-mono)",
                color: "var(--color-muted-foreground)",
                letterSpacing: "0.1em",
              }}
            >
              End session
            </span>
          </div>
        </button>
      </div>
    </aside>
  );
}
