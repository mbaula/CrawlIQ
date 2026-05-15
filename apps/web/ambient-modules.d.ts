declare module "d3-force-3d" {
  type CollideForce = {
    radius: (fn: (n: unknown) => number) => CollideForce;
    strength: (v: number) => CollideForce;
  };
  type RadialForce = {
    radius: (fn: ((n: unknown) => number) | number) => RadialForce;
    x: (v: number) => RadialForce;
    y: (v: number) => RadialForce;
    strength: (fn: ((n: unknown) => number) | number) => RadialForce;
  };
  export function forceCollide(): CollideForce;
  export function forceRadial(radius?: number | ((n: unknown) => number), x?: number, y?: number): RadialForce;
}
