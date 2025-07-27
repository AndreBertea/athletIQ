"use client"

import * as React from "react"
import {
  Area,
  AreaChart as RechartsAreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { cn } from "../../lib/utils"

interface AreaChartProps extends React.HTMLAttributes<HTMLDivElement> {
  data: any[]
  index: string
  categories: string[]
  colors?: string[]
  valueFormatter?: (value: number) => string
  startEndOnly?: boolean
  showXAxis?: boolean
  showYAxis?: boolean
  yAxisWidth?: number
  showAnimation?: boolean
  showTooltip?: boolean
  showGrid?: boolean
  autoMinValue?: boolean
  minValue?: number
  maxValue?: number
}

const AreaChart = React.forwardRef<HTMLDivElement, AreaChartProps>(
  (
    {
      data,
      index,
      categories,
      colors = ["hsl(var(--chart-1))", "hsl(var(--chart-2))", "hsl(var(--chart-3))", "hsl(var(--chart-4))", "hsl(var(--chart-5))"],
      valueFormatter = (value: number) => {
        if (typeof value === 'number' && !isNaN(value)) {
          return value.toString()
        }
        return '0'
      },
      startEndOnly = false,
      showXAxis = true,
      showYAxis = true,
      yAxisWidth = 56,
      showAnimation = true,
      showTooltip = true,
      showGrid = true,
      autoMinValue = true,
      minValue,
      maxValue,
      className,
      ...otherProps
    },
    ref
  ) => {
    const id = React.useId()

    return (
      <div
        ref={ref}
        className={cn("h-[350px] w-full", className)}
        {...otherProps}
      >
        <ResponsiveContainer width="100%" height="100%">
          <RechartsAreaChart
            data={data}
            margin={{
              top: 5,
              right: 10,
              left: 10,
              bottom: 0,
            }}
          >
            {showGrid && (
              <defs>
                {categories.map((category, idx) => (
                  <linearGradient
                    key={category}
                    id={`${id}-${category}`}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor={colors[idx % colors.length]}
                      stopOpacity={0.4}
                    />
                    <stop
                      offset="100%"
                      stopColor={colors[idx % colors.length]}
                      stopOpacity={0}
                    />
                  </linearGradient>
                ))}
              </defs>
            )}
            {showXAxis && (
              <XAxis
                dataKey={index}
                tick={{ transform: "translate(0, 6)" }}
                ticks={
                  startEndOnly
                    ? data.length > 0
                      ? [data[0][index], data[data.length - 1][index]]
                      : []
                    : undefined
                }
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => {
                  // Pour l'axe X (dates), on retourne directement la valeur
                  return value
                }}
                minTickGap={5}
              />
            )}
            {showYAxis && (
              <YAxis
                tick={{ transform: "translate(-3, 0)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => {
                  // S'assurer que la valeur est un nombre avant d'appliquer le formateur
                  if (typeof value === 'number' && !isNaN(value)) {
                    return valueFormatter(value)
                  }
                  return value.toString()
                }}
                width={yAxisWidth}
                tickMargin={8}
                domain={autoMinValue ? [0, "dataMax + 1"] : [minValue ?? 0, maxValue ?? "dataMax + 1"]}
              />
            )}
            {showTooltip && (
              <Tooltip
                content={({ active, payload, label }) => {
                  if (active && payload && payload.length) {
                    // Trier les payloads selon l'ordre souhaité
                    const sortedPayloads = [...payload].sort((a, b) => {
                      const getOrder = (name: string) => {
                        if (name === 'distance') return 1
                        if (name === 'elevation') return 2
                        if (name === 'duration') return 3
                        if (name === 'pace') return 4
                        return 5
                      }
                      return getOrder(a.name) - getOrder(b.name)
                    })

                    return (
                      <div className="rounded-lg border bg-background p-2 shadow-sm">
                        <div className="space-y-2">
                          {/* Date */}
                          <div className="flex flex-col">
                            <span className="text-[0.70rem] uppercase text-muted-foreground">
                              Date
                            </span>
                            <span className="font-bold text-muted-foreground">
                              {label}
                            </span>
                          </div>
                          
                          {/* Métriques dans l'ordre souhaité */}
                          {sortedPayloads.map((payload: any, idx: number) => (
                            <div key={payload.name} className="flex flex-col">
                              <span className="text-[0.70rem] uppercase text-muted-foreground">
                                {payload.name === 'distance' ? 'Distance' :
                                 payload.name === 'elevation' ? 'Dénivelé' :
                                 payload.name === 'duration' ? 'Durée' :
                                 payload.name === 'pace' ? 'Pace' : payload.name}
                              </span>
                              <span className="font-bold" style={{ color: colors[idx % colors.length] }}>
                                {valueFormatter(payload.value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  }
                  return null
                }}
              />
            )}
            {categories.map((category, idx) => (
              <Area
                key={category}
                type="monotone"
                dataKey={category}
                stroke={colors[idx % colors.length]}
                strokeWidth={2}
                fill={`url(#${id}-${category})`}
                isAnimationActive={showAnimation}
              />
            ))}
          </RechartsAreaChart>
        </ResponsiveContainer>
      </div>
    )
  }
)
AreaChart.displayName = "AreaChart"

export { AreaChart } 