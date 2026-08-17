"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/context/Authcontext";

export default function Header() {
  const t = useTranslations();
  const { user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  const displayName =
    user?.name ||
    user?.preferred_username ||
    user?.email ||
    t("user");

  useEffect(() => {
    if (!profileOpen) return;

    const onPointerDown = (event: MouseEvent) => {
      if (
        profileRef.current &&
        !profileRef.current.contains(event.target as Node)
      ) {
        setProfileOpen(false);
      }
    };

    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [profileOpen]);

  return (
    <header className="z-20 w-full shrink-0 bg-white">
      <div className="mx-auto flex h-[60px] w-full max-w-[1440px] items-center justify-between px-4">
        <Link
          href="/"
          className="ml-[11px] flex h-[32px] items-center gap-[7.2px] shrink-0"
        >
          <Image
            src="/openg2p-icon.svg"
            alt="OpenG2P"
            width={32}
            height={32}
            priority
            className="h-[32px] w-[32px] shrink-0 object-contain"
          />
          <span className="whitespace-nowrap text-[20px] font-medium leading-none tracking-normal text-black">
            {t("master_data")}
          </span>
        </Link>

        <div className="flex items-center gap-4">
          <button
            type="button"
            aria-label={t("notifications")}
            className="flex h-8 w-8 items-center justify-center cursor-pointer"
          >
            <Image
              src="/notification.png"
              alt=""
              width={20}
              height={20}
              className="h-5 w-5 object-contain"
            />
          </button>

          <span className="whitespace-nowrap text-[15px] font-normal leading-none text-black">
            {t("hi_user", { name: displayName })}
          </span>

          <div ref={profileRef} className="relative">
            <button
              type="button"
              aria-label={t("user")}
              aria-expanded={profileOpen}
              aria-haspopup="menu"
              onClick={() => setProfileOpen((open) => !open)}
              className="h-9 w-9 shrink-0 cursor-pointer overflow-hidden rounded-full"
            >
              <Image
                src="/profile.png"
                alt={displayName}
                width={36}
                height={36}
                className="h-full w-full object-cover"
              />
            </button>

            {profileOpen && (
              <div
                role="menu"
                className="absolute right-0 top-11 z-50 min-w-[140px] rounded-lg border border-black/10 bg-white py-2 shadow-[0_4px_20px_rgba(0,0,0,0.12)]"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setProfileOpen(false);
                    logout();
                  }}
                  className="flex w-full cursor-pointer items-center gap-2 px-4 py-2.5 text-left text-[14px] font-semibold text-black hover:bg-black/5"
                >
                  <Image
                    src="/logout.png"
                    alt=""
                    width={18}
                    height={18}
                    className="h-[18px] w-[18px] object-contain"
                  />
                  {t("logout")}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
