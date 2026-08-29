import { redirect } from "next/navigation"
import { defaultStationHref } from "../src/workspace/default-station"

export default function Home() {
  redirect(defaultStationHref())
}
