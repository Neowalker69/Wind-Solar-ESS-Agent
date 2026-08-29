"use client"

import type { FormEvent, ReactNode } from "react"
import { useEffect, useState } from "react"

import {
  authenticateStation,
  clearStationToken,
  readStationToken,
  validateStationToken
} from "./station-auth"

type LoginState = "checking" | "login" | "authenticated"

export function ControlLoginGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LoginState>("checking")
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let active = true
    const token = readStationToken()
    if (!token) {
      setState("login")
      return () => { active = false }
    }

    validateStationToken(token)
      .then((valid) => {
        if (!active) return
        if (valid) {
          setState("authenticated")
        } else {
          clearStationToken()
          setState("login")
        }
      })
      .catch(() => {
        if (!active) return
        clearStationToken()
        setError("登录状态校验失败，请重新登录")
        setState("login")
      })

    return () => { active = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setSubmitting(true)
    try {
      await authenticateStation(username, password)
      setPassword("")
      setState("authenticated")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登录失败")
    } finally {
      setSubmitting(false)
    }
  }

  if (state === "authenticated") return children

  return (
    <main className="control-login-shell">
      <section className="control-login-card" aria-busy={state === "checking"}>
        <div className="control-login-mark">AH</div>
        <p className="control-login-kicker">Agent Harness Control</p>
        <h1>数字孪生工作台登录</h1>
        {state === "checking" ? (
          <p className="control-login-checking">正在校验登录凭据…</p>
        ) : (
          <form className="control-login-form" onSubmit={submit}>
            <label>
              用户名
              <input
                autoComplete="username"
                name="username"
                onChange={(event) => setUsername(event.target.value)}
                required
                value={username}
              />
            </label>
            <label>
              密码
              <input
                autoComplete="current-password"
                autoFocus
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            {error ? <p className="control-login-error" role="alert">{error}</p> : null}
            <button disabled={submitting} type="submit">
              {submitting ? "正在登录…" : "登录 Control"}
            </button>
          </form>
        )}
        <p className="control-login-hint">
          本地演示默认账号：admin / admin123。公开部署前请在 .env 中修改。
        </p>
      </section>
    </main>
  )
}
