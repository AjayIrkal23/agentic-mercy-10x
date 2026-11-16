/*! hf-paper 2026-10-11: Paper Shaders @paper-design/shaders 0.0.81 + @paper-design/shaders-react 0.0.81 (Apache-2.0, https://github.com/paper-design/shaders), bundled with React shimmed out, plus the ghost-editor HyperFrames seek driver. See THIRD_PARTY.md. */
(()=>{var ja=Object.defineProperty;var Ka=(e,o)=>{for(var a in o)ja(e,a,{get:o[a],enumerable:!0})};var At=`#version 300 es
precision mediump float;

layout(location = 0) in vec4 a_position;

uniform vec2 u_resolution;
uniform float u_pixelRatio;
uniform float u_imageAspectRatio;
uniform float u_originX;
uniform float u_originY;
uniform float u_worldWidth;
uniform float u_worldHeight;
uniform float u_fit;
uniform float u_scale;
uniform float u_rotation;
uniform float u_offsetX;
uniform float u_offsetY;

out vec2 v_objectUV;
out vec2 v_objectBoxSize;
out vec2 v_responsiveUV;
out vec2 v_responsiveBoxGivenSize;
out vec2 v_patternUV;
out vec2 v_patternBoxSize;
out vec2 v_imageUV;

vec3 getBoxSize(float boxRatio, vec2 givenBoxSize) {
  vec2 box = vec2(0.);
  // fit = none
  box.x = boxRatio * min(givenBoxSize.x / boxRatio, givenBoxSize.y);
  float noFitBoxWidth = box.x;
  if (u_fit == 1.) { // fit = contain
    box.x = boxRatio * min(u_resolution.x / boxRatio, u_resolution.y);
  } else if (u_fit == 2.) { // fit = cover
    box.x = boxRatio * max(u_resolution.x / boxRatio, u_resolution.y);
  }
  box.y = box.x / boxRatio;
  return vec3(box, noFitBoxWidth);
}

void main() {
  gl_Position = a_position;

  vec2 uv = gl_Position.xy * .5;
  vec2 boxOrigin = vec2(.5 - u_originX, u_originY - .5);
  vec2 givenBoxSize = vec2(u_worldWidth, u_worldHeight);
  givenBoxSize = max(givenBoxSize, vec2(1.)) * u_pixelRatio;
  float r = u_rotation * 3.14159265358979323846 / 180.;
  mat2 graphicRotation = mat2(cos(r), sin(r), -sin(r), cos(r));
  vec2 graphicOffset = vec2(-u_offsetX, u_offsetY);


  // ===================================================

  float fixedRatio = 1.;
  vec2 fixedRatioBoxGivenSize = vec2(
  (u_worldWidth == 0.) ? u_resolution.x : givenBoxSize.x,
  (u_worldHeight == 0.) ? u_resolution.y : givenBoxSize.y
  );

  v_objectBoxSize = getBoxSize(fixedRatio, fixedRatioBoxGivenSize).xy;
  vec2 objectWorldScale = u_resolution.xy / v_objectBoxSize;

  v_objectUV = uv;
  v_objectUV *= objectWorldScale;
  v_objectUV += boxOrigin * (objectWorldScale - 1.);
  v_objectUV += graphicOffset;
  v_objectUV /= u_scale;
  v_objectUV = graphicRotation * v_objectUV;

  // ===================================================

  v_responsiveBoxGivenSize = vec2(
  (u_worldWidth == 0.) ? u_resolution.x : givenBoxSize.x,
  (u_worldHeight == 0.) ? u_resolution.y : givenBoxSize.y
  );
  float responsiveRatio = v_responsiveBoxGivenSize.x / v_responsiveBoxGivenSize.y;
  vec2 responsiveBoxSize = getBoxSize(responsiveRatio, v_responsiveBoxGivenSize).xy;
  vec2 responsiveBoxScale = u_resolution.xy / responsiveBoxSize;

  #ifdef ADD_HELPERS
  v_responsiveHelperBox = uv;
  v_responsiveHelperBox *= responsiveBoxScale;
  v_responsiveHelperBox += boxOrigin * (responsiveBoxScale - 1.);
  #endif

  v_responsiveUV = uv;
  v_responsiveUV *= responsiveBoxScale;
  v_responsiveUV += boxOrigin * (responsiveBoxScale - 1.);
  v_responsiveUV += graphicOffset;
  v_responsiveUV /= u_scale;
  v_responsiveUV.x *= responsiveRatio;
  v_responsiveUV = graphicRotation * v_responsiveUV;
  v_responsiveUV.x /= responsiveRatio;

  // ===================================================

  float patternBoxRatio = givenBoxSize.x / givenBoxSize.y;
  vec2 patternBoxGivenSize = vec2(
  (u_worldWidth == 0.) ? u_resolution.x : givenBoxSize.x,
  (u_worldHeight == 0.) ? u_resolution.y : givenBoxSize.y
  );
  patternBoxRatio = patternBoxGivenSize.x / patternBoxGivenSize.y;

  vec3 boxSizeData = getBoxSize(patternBoxRatio, patternBoxGivenSize);
  v_patternBoxSize = boxSizeData.xy;
  float patternBoxNoFitBoxWidth = boxSizeData.z;
  vec2 patternBoxScale = u_resolution.xy / v_patternBoxSize;

  v_patternUV = uv;
  v_patternUV += graphicOffset / patternBoxScale;
  v_patternUV += boxOrigin;
  v_patternUV -= boxOrigin / patternBoxScale;
  v_patternUV *= u_resolution.xy;
  v_patternUV /= u_pixelRatio;
  if (u_fit > 0.) {
    v_patternUV *= (patternBoxNoFitBoxWidth / v_patternBoxSize.x);
  }
  v_patternUV /= u_scale;
  v_patternUV = graphicRotation * v_patternUV;
  v_patternUV += boxOrigin / patternBoxScale;
  v_patternUV -= boxOrigin;
  // x100 is a default multiplier between vertex and fragmant shaders
  // we use it to avoid UV presision issues
  v_patternUV *= .01;

  // ===================================================

  vec2 imageBoxSize;
  if (u_fit == 1.) { // contain
    imageBoxSize.x = min(u_resolution.x / u_imageAspectRatio, u_resolution.y) * u_imageAspectRatio;
  } else if (u_fit == 2.) { // cover
    imageBoxSize.x = max(u_resolution.x / u_imageAspectRatio, u_resolution.y) * u_imageAspectRatio;
  } else {
    imageBoxSize.x = min(10.0, 10.0 / u_imageAspectRatio * u_imageAspectRatio);
  }
  imageBoxSize.y = imageBoxSize.x / u_imageAspectRatio;
  vec2 imageBoxScale = u_resolution.xy / imageBoxSize;

  v_imageUV = uv;
  v_imageUV *= imageBoxScale;
  v_imageUV += boxOrigin * (imageBoxScale - 1.);
  v_imageUV += graphicOffset;
  v_imageUV /= u_scale;
  v_imageUV.x *= u_imageAspectRatio;
  v_imageUV = graphicRotation * v_imageUV;
  v_imageUV.x /= u_imageAspectRatio;

  v_imageUV += .5;
  v_imageUV.y = 1. - v_imageUV.y;
}`;var Bt=1920*1080*4,Te=class{parentElement;canvasElement;gl;program=null;uniformLocations={};fragmentShader;rafId=null;lastRenderTime=0;currentFrame=0;speed=0;currentSpeed=0;providedUniforms;mipmaps=[];hasBeenDisposed=!1;resolutionChanged=!0;textures=new Map;minPixelRatio;maxPixelCount;isSafari=$a();uniformCache={};textureUnitMap=new Map;ownerDocument;constructor(o,a,t,l,i=0,c=0,r=2,m=Bt,s=[]){if(o?.nodeType===1)this.parentElement=o;else throw new Error("Paper Shaders: parent element must be an HTMLElement");if(this.ownerDocument=o.ownerDocument,!this.ownerDocument.querySelector("style[data-paper-shader]")){let p=this.ownerDocument.createElement("style");p.innerHTML=Za,p.setAttribute("data-paper-shader",""),this.ownerDocument.head.prepend(p)}let d=this.ownerDocument.createElement("canvas");this.canvasElement=d,this.parentElement.prepend(d),this.fragmentShader=a,this.providedUniforms=t,this.mipmaps=s,this.currentFrame=c,this.minPixelRatio=r,this.maxPixelCount=m;let u=d.getContext("webgl2",l);if(!u)throw new Error("Paper Shaders: WebGL is not supported in this browser");this.gl=u,this.initProgram(),this.setupPositionAttribute(),this.setupUniforms(),this.setUniformValues(this.providedUniforms),this.setupResizeObserver(),visualViewport?.addEventListener("resize",this.handleVisualViewportChange),this.setupIntersectionObserver(),this.setSpeed(i),this.parentElement.setAttribute("data-paper-shader",""),this.parentElement.paperShaderMount=this,this.ownerDocument.addEventListener("visibilitychange",this.handleDocumentVisibilityChange)}initProgram=()=>{let o=Ja(this.gl,At,this.fragmentShader);o&&(this.program=o)};setupPositionAttribute=()=>{let o=this.gl.getAttribLocation(this.program,"a_position"),a=this.gl.createBuffer();this.gl.bindBuffer(this.gl.ARRAY_BUFFER,a);let t=[-1,-1,1,-1,-1,1,-1,1,1,-1,1,1];this.gl.bufferData(this.gl.ARRAY_BUFFER,new Float32Array(t),this.gl.STATIC_DRAW),this.gl.enableVertexAttribArray(o),this.gl.vertexAttribPointer(o,2,this.gl.FLOAT,!1,0,0)};setupUniforms=()=>{let o={u_time:this.gl.getUniformLocation(this.program,"u_time"),u_pixelRatio:this.gl.getUniformLocation(this.program,"u_pixelRatio"),u_resolution:this.gl.getUniformLocation(this.program,"u_resolution")};Object.entries(this.providedUniforms).forEach(([a,t])=>{if(o[a]=this.gl.getUniformLocation(this.program,a),t instanceof HTMLImageElement){let l=`${a}AspectRatio`;o[l]=this.gl.getUniformLocation(this.program,l)}}),this.uniformLocations=o};renderScale=1;parentWidth=0;parentHeight=0;parentDevicePixelWidth=0;parentDevicePixelHeight=0;devicePixelsSupported=!1;intersectionObserver=null;isInViewport=!0;resizeObserver=null;setupResizeObserver=()=>{this.resizeObserver=new ResizeObserver(([o])=>{if(o?.borderBoxSize[0]){let a=o.devicePixelContentBoxSize?.[0];a!==void 0&&(this.devicePixelsSupported=!0,this.parentDevicePixelWidth=a.inlineSize,this.parentDevicePixelHeight=a.blockSize),this.parentWidth=o.borderBoxSize[0].inlineSize,this.parentHeight=o.borderBoxSize[0].blockSize}this.handleResize()}),this.resizeObserver.observe(this.parentElement)};setupIntersectionObserver=()=>{let o=this.ownerDocument.defaultView;o?.IntersectionObserver&&(this.intersectionObserver=new o.IntersectionObserver(([a])=>{this.isInViewport=a?.isIntersecting??!0,this.updateCurrentSpeed()}),this.intersectionObserver.observe(this.parentElement))};handleVisualViewportChange=()=>{this.resizeObserver?.disconnect(),this.setupResizeObserver()};handleResize=()=>{let o=0,a=0,t=Math.max(1,window.devicePixelRatio),l=visualViewport?.scale??1;if(this.devicePixelsSupported){let d=Math.max(1,this.minPixelRatio/t);o=this.parentDevicePixelWidth*d*l,a=this.parentDevicePixelHeight*d*l}else{let d=Math.max(t,this.minPixelRatio)*l;if(this.isSafari){let u=er(this.ownerDocument);d*=Math.max(1,u)}o=Math.round(this.parentWidth)*d,a=Math.round(this.parentHeight)*d}let i=Math.sqrt(this.maxPixelCount)/Math.sqrt(o*a),c=Math.min(1,i),r=Math.round(o*c),m=Math.round(a*c),s=r/Math.round(this.parentWidth);(this.canvasElement.width!==r||this.canvasElement.height!==m||this.renderScale!==s)&&(this.renderScale=s,this.canvasElement.width=r,this.canvasElement.height=m,this.resolutionChanged=!0,this.gl.viewport(0,0,this.gl.canvas.width,this.gl.canvas.height),this.render(performance.now()))};render=o=>{if(this.hasBeenDisposed)return;if(this.program===null){console.warn("Tried to render before program or gl was initialized");return}let a=o-this.lastRenderTime;this.lastRenderTime=o,this.currentSpeed!==0&&(this.currentFrame+=a*this.currentSpeed),this.gl.clear(this.gl.COLOR_BUFFER_BIT),this.gl.useProgram(this.program),this.gl.uniform1f(this.uniformLocations.u_time,this.currentFrame*.001),this.resolutionChanged&&(this.gl.uniform2f(this.uniformLocations.u_resolution,this.gl.canvas.width,this.gl.canvas.height),this.gl.uniform1f(this.uniformLocations.u_pixelRatio,this.renderScale),this.resolutionChanged=!1),this.gl.drawArrays(this.gl.TRIANGLES,0,6),this.currentSpeed!==0?this.requestRender():this.rafId=null};requestRender=()=>{this.rafId!==null&&cancelAnimationFrame(this.rafId),this.rafId=requestAnimationFrame(this.render)};setTextureUniform=(o,a)=>{if(!a.complete||a.naturalWidth===0)throw new Error(`Paper Shaders: image for uniform ${o} must be fully loaded`);let t=this.textures.get(o);t&&this.gl.deleteTexture(t),this.textureUnitMap.has(o)||this.textureUnitMap.set(o,this.textureUnitMap.size);let l=this.textureUnitMap.get(o);this.gl.activeTexture(this.gl.TEXTURE0+l);let i=this.gl.createTexture();this.gl.bindTexture(this.gl.TEXTURE_2D,i),this.gl.texParameteri(this.gl.TEXTURE_2D,this.gl.TEXTURE_WRAP_S,this.gl.CLAMP_TO_EDGE),this.gl.texParameteri(this.gl.TEXTURE_2D,this.gl.TEXTURE_WRAP_T,this.gl.CLAMP_TO_EDGE),this.gl.texParameteri(this.gl.TEXTURE_2D,this.gl.TEXTURE_MIN_FILTER,this.gl.LINEAR),this.gl.texParameteri(this.gl.TEXTURE_2D,this.gl.TEXTURE_MAG_FILTER,this.gl.LINEAR),this.gl.texImage2D(this.gl.TEXTURE_2D,0,this.gl.RGBA,this.gl.RGBA,this.gl.UNSIGNED_BYTE,a),this.mipmaps.includes(o)&&(this.gl.generateMipmap(this.gl.TEXTURE_2D),this.gl.texParameteri(this.gl.TEXTURE_2D,this.gl.TEXTURE_MIN_FILTER,this.gl.LINEAR_MIPMAP_LINEAR));let c=this.gl.getError();if(c!==this.gl.NO_ERROR||i===null){console.error("Paper Shaders: WebGL error when uploading texture:",c);return}this.textures.set(o,i);let r=this.uniformLocations[o];if(r){this.gl.uniform1i(r,l);let m=`${o}AspectRatio`,s=this.uniformLocations[m];if(s){let d=a.naturalWidth/a.naturalHeight;this.gl.uniform1f(s,d)}}};areUniformValuesEqual=(o,a)=>o===a?!0:Array.isArray(o)&&Array.isArray(a)&&o.length===a.length?o.every((t,l)=>this.areUniformValuesEqual(t,a[l])):!1;setUniformValues=o=>{this.gl.useProgram(this.program),Object.entries(o).forEach(([a,t])=>{let l=t;if(t instanceof HTMLImageElement&&(l=`${t.src.slice(0,200)}|${t.naturalWidth}x${t.naturalHeight}`),this.areUniformValuesEqual(this.uniformCache[a],l))return;this.uniformCache[a]=l;let i=this.uniformLocations[a];if(!i){console.warn(`Uniform location for ${a} not found`);return}if(t instanceof HTMLImageElement)this.setTextureUniform(a,t);else if(Array.isArray(t)){let c=null,r=null;if(t[0]!==void 0&&Array.isArray(t[0])){let m=t[0].length;if(t.every(s=>s.length===m))c=t.flat(),r=m;else{console.warn(`All child arrays must be the same length for ${a}`);return}}else c=t,r=c.length;switch(r){case 2:this.gl.uniform2fv(i,c);break;case 3:this.gl.uniform3fv(i,c);break;case 4:this.gl.uniform4fv(i,c);break;case 9:this.gl.uniformMatrix3fv(i,!1,c);break;case 16:this.gl.uniformMatrix4fv(i,!1,c);break;default:console.warn(`Unsupported uniform array length: ${r}`)}}else typeof t=="number"?this.gl.uniform1f(i,t):typeof t=="boolean"?this.gl.uniform1i(i,t?1:0):console.warn(`Unsupported uniform type for ${a}: ${typeof t}`)})};getCurrentFrame=()=>this.currentFrame;setFrame=o=>{this.currentFrame=o,this.lastRenderTime=performance.now(),this.render(performance.now())};setSpeed=(o=1)=>{this.speed=o,this.updateCurrentSpeed()};updateCurrentSpeed=()=>{this.setCurrentSpeed(this.ownerDocument.hidden||!this.isInViewport?0:this.speed)};setCurrentSpeed=o=>{this.currentSpeed=o,this.rafId===null&&o!==0&&(this.lastRenderTime=performance.now(),this.rafId=requestAnimationFrame(this.render)),this.rafId!==null&&o===0&&(cancelAnimationFrame(this.rafId),this.rafId=null)};setMaxPixelCount=(o=Bt)=>{this.maxPixelCount=o,this.handleResize()};setMinPixelRatio=(o=2)=>{this.minPixelRatio=o,this.handleResize()};setUniforms=o=>{this.setUniformValues(o),this.providedUniforms={...this.providedUniforms,...o},this.render(performance.now())};handleDocumentVisibilityChange=()=>{this.updateCurrentSpeed()};dispose=()=>{this.hasBeenDisposed=!0,this.rafId!==null&&(cancelAnimationFrame(this.rafId),this.rafId=null),this.gl&&this.program&&(this.textures.forEach(o=>{this.gl.deleteTexture(o)}),this.textures.clear(),this.gl.deleteProgram(this.program),this.program=null,this.gl.bindBuffer(this.gl.ARRAY_BUFFER,null),this.gl.bindBuffer(this.gl.ELEMENT_ARRAY_BUFFER,null),this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,null),this.gl.bindFramebuffer(this.gl.FRAMEBUFFER,null),this.gl.getError()),this.resizeObserver&&(this.resizeObserver.disconnect(),this.resizeObserver=null),this.intersectionObserver&&(this.intersectionObserver.disconnect(),this.intersectionObserver=null),visualViewport?.removeEventListener("resize",this.handleVisualViewportChange),this.ownerDocument.removeEventListener("visibilitychange",this.handleDocumentVisibilityChange),this.uniformLocations={},this.canvasElement.remove(),delete this.parentElement.paperShaderMount}};function kt(e,o,a){let t=e.createShader(o);return t?(e.shaderSource(t,a),e.compileShader(t),e.getShaderParameter(t,e.COMPILE_STATUS)?t:(console.error("An error occurred compiling the shaders: "+e.getShaderInfoLog(t)),e.deleteShader(t),null)):null}function Ja(e,o,a){let t=e.getShaderPrecisionFormat(e.FRAGMENT_SHADER,e.MEDIUM_FLOAT),l=t?t.precision:null;l&&l<23&&(o=o.replace(/precision\s+(lowp|mediump)\s+float;/g,"precision highp float;"),a=a.replace(/precision\s+(lowp|mediump)\s+float/g,"precision highp float").replace(/\b(uniform|varying|attribute)\s+(lowp|mediump)\s+(\w+)/g,"$1 highp $3"));let i=kt(e,e.VERTEX_SHADER,o),c=kt(e,e.FRAGMENT_SHADER,a);if(!i||!c)return null;let r=e.createProgram();return r?(e.attachShader(r,i),e.attachShader(r,c),e.linkProgram(r),e.getProgramParameter(r,e.LINK_STATUS)?(e.detachShader(r,i),e.detachShader(r,c),e.deleteShader(i),e.deleteShader(c),r):(console.error("Unable to initialize the shader program: "+e.getProgramInfoLog(r)),e.deleteProgram(r),e.deleteShader(i),e.deleteShader(c),null)):null}var Za=`@layer paper-shaders {
  :where([data-paper-shader]) {
    isolation: isolate;
    position: relative;

    & canvas {
      contain: strict;
      display: block;
      position: absolute;
      inset: 0;
      z-index: -1;
      width: 100%;
      height: 100%;
      border-radius: inherit;
      corner-shape: inherit;
    }
  }
}`;function Mo(e){return"paperShaderMount"in e}function $a(){let e=navigator.userAgent.toLowerCase();return e.includes("safari")&&!e.includes("chrome")&&!e.includes("android")}function er(e){let o=visualViewport?.scale??1,a=visualViewport?.width??window.innerWidth,t=window.innerWidth-e.documentElement.clientWidth,l=o*a+t,i=outerWidth/l,c=Math.round(100*i);return c%5===0?c/100:c===33?1/3:c===67?2/3:c===133?4/3:i}var h={fit:"contain",scale:1,rotation:0,offsetX:0,offsetY:0,originX:.5,originY:.5,worldWidth:0,worldHeight:0},M={fit:"none",scale:1,rotation:0,offsetX:0,offsetY:0,originX:.5,originY:.5,worldWidth:0,worldHeight:0},F={none:0,contain:1,cover:2};var P=`
#define TWO_PI 6.28318530718
#define PI 3.14159265358979323846
`,L=`
vec2 rotate(vec2 uv, float th) {
  return mat2(cos(th), sin(th), -sin(th), cos(th)) * uv;
}
`,Ge=`
  float hash11(float p) {
    p = fract(p * 0.3183099) + 0.1;
    p *= p + 19.19;
    return fract(p * p);
  }
`,me=`
  float hash21(vec2 p) {
    p = fract(p * vec2(0.3183099, 0.3678794)) + 0.1;
    p += dot(p, p + 19.19);
    return fract(p.x * p.y);
  }
`,Ft=`
  vec2 hash22(vec2 p) {
    p = fract(p * vec2(0.3183099, 0.3678794)) + 0.1;
    p += dot(p, p.yx + 19.19);
    return fract(vec2(p.x * p.y, p.x + p.y));
  }
`,ze=`
  float randomR(vec2 p) {
    vec2 uv = floor(p) / 100. + .5;
    return texture(u_noiseTexture, fract(uv)).r;
  }
`,qe=`
  vec2 randomGB(vec2 p) {
    vec2 uv = floor(p) / 100. + .5;
    return texture(u_noiseTexture, fract(uv)).gb;
  }
`,Z=`
  color += 1. / 256. * (fract(sin(dot(.014 * gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453123) - .5);
`,Me=`
vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
float snoise(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439,
    -0.577350269189626, 0.024390243902439);
  vec2 i = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1;
  i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0))
    + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy),
      dot(x12.zw, x12.zw)), 0.0);
  m = m * m;
  m = m * m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
  vec3 g;
  g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}
`;var io={maxColorCount:10},Po=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colors[${io.maxColorCount}];
uniform float u_colorsCount;

uniform float u_distortion;
uniform float u_swirl;
uniform float u_grainMixer;
uniform float u_grainOverlay;

in vec2 v_objectUV;
out vec4 fragColor;

${P}
${L}
${me}

float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

float noise(vec2 n, vec2 seedOffset) {
  return valueNoise(n + seedOffset);
}

vec2 getPosition(int i, float t) {
  float a = float(i) * .37;
  float b = .6 + fract(float(i) / 3.) * .9;
  float c = .8 + fract(float(i + 1) / 4.);

  float x = sin(t * b + a);
  float y = cos(t * c + a * 1.5);

  return .5 + .5 * vec2(x, y);
}

void main() {
  vec2 uv = v_objectUV;
  uv += .5;
  vec2 grainUV = uv * 1000.;

  float mixerGrain = 0.;
  if (u_grainMixer > 0.) {
    mixerGrain = .4 * u_grainMixer * (noise(grainUV, vec2(0.)) - .5);
  }

  const float firstFrameOffset = 41.5;
  float t = .5 * (u_time + firstFrameOffset);

  float radius = smoothstep(0., 1., length(uv - .5));
  float center = 1. - radius;
  for (float i = 1.; i <= 2.; i++) {
    uv.x += u_distortion * center / i * sin(t + i * .4 * smoothstep(.0, 1., uv.y)) * cos(.2 * t + i * 2.4 * smoothstep(.0, 1., uv.y));
    uv.y += u_distortion * center / i * cos(t + i * 2. * smoothstep(.0, 1., uv.x));
  }

  vec2 uvRotated = uv;
  uvRotated -= vec2(.5);
  float angle = 3. * u_swirl * radius;
  uvRotated = rotate(uvRotated, -angle);
  uvRotated += vec2(.5);

  vec3 color = vec3(0.);
  float opacity = 0.;
  float totalWeight = 0.;

  for (int i = 0; i < ${io.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;

    vec2 pos = getPosition(i, t) + mixerGrain;
    vec3 colorFraction = u_colors[i].rgb * u_colors[i].a;
    float opacityFraction = u_colors[i].a;

    float dist = length(uvRotated - pos);

    dist = pow(dist, 3.5);
    float weight = 1. / (dist + 1e-3);
    color += colorFraction * weight;
    opacity += opacityFraction * weight;
    totalWeight += weight;
  }

  color /= max(1e-4, totalWeight);
  opacity /= max(1e-4, totalWeight);

  if (u_grainOverlay > 0.) {
    float grainOverlay = valueNoise(rotate(grainUV, 1.) + vec2(3.));
    grainOverlay = mix(grainOverlay, valueNoise(rotate(grainUV, 2.) + vec2(-1.)), .5);
    grainOverlay = pow(grainOverlay, 1.3);

    float grainOverlayV = grainOverlay * 2. - 1.;
    vec3 grainOverlayColor = vec3(step(0., grainOverlayV));
    float grainOverlayStrength = u_grainOverlay * abs(grainOverlayV);
    grainOverlayStrength = pow(grainOverlayStrength, .8);
    color = mix(color, grainOverlayColor, .35 * grainOverlayStrength);

    opacity += .5 * grainOverlayStrength;
  }
  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`;var je={maxColorCount:10,maxNoiseIterations:8},Io=`#version 300 es
precision mediump float;

uniform float u_time;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${je.maxColorCount}];
uniform float u_colorsCount;

uniform float u_thickness;
uniform float u_radius;
uniform float u_innerShape;
uniform float u_noiseScale;
uniform float u_noiseIterations;

in vec2 v_objectUV;

out vec4 fragColor;

${P}
${ze}
float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = randomR(i);
  float b = randomR(i + vec2(1.0, 0.0));
  float c = randomR(i + vec2(0.0, 1.0));
  float d = randomR(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}
vec2 fbm(vec2 n0, vec2 n1) {
  vec2 total = vec2(0.0);
  float amplitude = .4;
  for (int i = 0; i < ${je.maxNoiseIterations}; i++) {
    if (i >= int(u_noiseIterations)) break;
    total.x += valueNoise(n0) * amplitude;
    total.y += valueNoise(n1) * amplitude;
    n0 *= 1.99;
    n1 *= 1.99;
    amplitude *= 0.65;
  }
  return total;
}

float getNoise(vec2 uv, vec2 pUv, float t) {
  vec2 pUvLeft = pUv + .03 * t;
  float period = max(abs(u_noiseScale * TWO_PI), 1e-6);
  vec2 pUvRight = vec2(fract(pUv.x / period) * period, pUv.y) + .03 * t;
  vec2 noise = fbm(pUvLeft, pUvRight);
  return mix(noise.y, noise.x, smoothstep(-.25, .25, uv.x));
}

float getRingShape(vec2 uv) {
  float radius = u_radius;
  float thickness = u_thickness;

  float distance = length(uv);
  float ringValue = 1. - smoothstep(radius, radius + thickness, distance);
  ringValue *= smoothstep(radius - pow(u_innerShape, 3.) * thickness, radius, distance);

  return ringValue;
}

void main() {
  vec2 shape_uv = v_objectUV;

  float t = u_time;

  float cycleDuration = 3.;
  float period2 = 2.0 * cycleDuration;
  float localTime1 = fract((0.1 * t + cycleDuration) / period2) * period2;
  float localTime2 = fract((0.1 * t) / period2) * period2;
  float timeBlend = .5 + .5 * sin(.1 * t * PI / cycleDuration - .5 * PI);

  float atg = atan(shape_uv.y, shape_uv.x) + .001;
  float l = length(shape_uv);
  float radialOffset = .5 * l - inversesqrt(max(1e-4, l));
  vec2 polar_uv1 = vec2(atg, localTime1 - radialOffset) * u_noiseScale;
  vec2 polar_uv2 = vec2(atg, localTime2 - radialOffset) * u_noiseScale;
  
  float noise1 = getNoise(shape_uv, polar_uv1, t);
  float noise2 = getNoise(shape_uv, polar_uv2, t);

  float noise = mix(noise1, noise2, timeBlend);

  shape_uv *= (.8 + 1.2 * noise);

  float ringShape = getRingShape(shape_uv);

  float mixer = ringShape * ringShape * (u_colorsCount - 1.);
  int idxLast = int(u_colorsCount) - 1;
  vec4 gradient = u_colors[idxLast];
  gradient.rgb *= gradient.a;
  for (int i = ${je.maxColorCount} - 2; i >= 0; i--) {
    float localT = clamp(mixer - float(idxLast - i - 1), 0., 1.);
    vec4 c = u_colors[i];
    c.rgb *= c.a;
    gradient = mix(gradient, c, localT);
  }

  vec3 color = gradient.rgb * ringShape;
  float opacity = gradient.a * ringShape;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1. - opacity);
  opacity = opacity + u_colorBack.a * (1. - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var Ro=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colorFront;
uniform vec4 u_colorMid;
uniform vec4 u_colorBack;
uniform float u_brightness;
uniform float u_contrast;

in vec2 v_patternUV;

out vec4 fragColor;

${L}

float neuroShape(vec2 uv, float t) {
  vec2 sine_acc = vec2(0.);
  vec2 res = vec2(0.);
  float scale = 8.;

  for (int j = 0; j < 15; j++) {
    uv = rotate(uv, 1.);
    sine_acc = rotate(sine_acc, 1.);
    vec2 layer = uv * scale + float(j) + sine_acc - t;
    sine_acc += sin(layer);
    res += (.5 + .5 * cos(layer)) / scale;
    scale *= (1.2);
  }
  return res.x + res.y;
}

void main() {
  vec2 shape_uv = v_patternUV;
  shape_uv *= .13;

  float t = .5 * u_time;

  float noise = neuroShape(shape_uv, t);

  noise = (1. + u_brightness) * noise * noise;
  noise = pow(noise, .7 + 6. * u_contrast);
  noise = min(1.4, noise);

  float blend = smoothstep(0.7, 1.4, noise);

  vec4 frontC = u_colorFront;
  frontC.rgb *= frontC.a;
  vec4 midC = u_colorMid;
  midC.rgb *= midC.a;
  vec4 blendFront = mix(midC, frontC, blend);

  float safeNoise = max(noise, 0.0);
  vec3 color = blendFront.rgb * safeNoise;
  float opacity = clamp(blendFront.a * safeNoise, 0., 1.);

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1. - opacity);
  opacity = opacity + u_colorBack.a * (1. - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var so={maxColorCount:10},Vo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${so.maxColorCount}];
uniform float u_colorsCount;
uniform float u_stepsPerColor;
uniform float u_size;
uniform float u_sizeRange;
uniform float u_spreading;

in vec2 v_patternUV;

out vec4 fragColor;

${P}
${L}
${ze}
${qe}


vec3 voronoiShape(vec2 uv, float time) {
  vec2 i_uv = floor(uv);
  vec2 f_uv = fract(uv);

  float spreading = .25 * clamp(u_spreading, 0., 1.);

  float minDist = 1.;
  vec2 randomizer = vec2(0.);
  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 tileOffset = vec2(float(x), float(y));
      vec2 rand = randomGB(i_uv + tileOffset);
      vec2 cellCenter = vec2(.5 + 1e-4);
      cellCenter += spreading * cos(time + TWO_PI * rand);
      cellCenter -= .5;
      cellCenter = rotate(cellCenter, randomR(vec2(rand.x, rand.y)) + .1 * time);
      cellCenter += .5;
      float dist = length(tileOffset + cellCenter - f_uv);
      if (dist < minDist) {
        minDist = dist;
        randomizer = rand;
      }
    }
  }

  return vec3(minDist, randomizer);
}

void main() {

  vec2 shape_uv = v_patternUV;
  shape_uv *= 1.5;

  const float firstFrameOffset = -10.;
  float t = u_time + firstFrameOffset;

  vec3 voronoi = voronoiShape(shape_uv, t) + 1e-4;

  float radius = .25 * clamp(u_size, 0., 1.) - .5 * clamp(u_sizeRange, 0., 1.) * voronoi[2];
  float dist = voronoi[0];
  float edgeWidth = fwidth(dist);
  float dots = 1. - smoothstep(radius - edgeWidth, radius + edgeWidth, dist);

  float shape = voronoi[1];

  float mixer = shape * (u_colorsCount - 1.);
  mixer = (shape - .5 / u_colorsCount) * u_colorsCount;
  float steps = max(1., u_stepsPerColor);

  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;
  for (int i = 1; i < ${so.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;
    float localT = clamp(mixer - float(i - 1), 0.0, 1.0);
    localT = round(localT * steps) / steps;
    vec4 c = u_colors[i];
    c.rgb *= c.a;
    gradient = mix(gradient, c, localT);
  }

  if ((mixer < 0.) || (mixer > (u_colorsCount - 1.))) {
    float localT = mixer + 1.;
    if (mixer > (u_colorsCount - 1.)) {
      localT = mixer - (u_colorsCount - 1.);
    }
    localT = round(localT * steps) / steps;
    vec4 cFst = u_colors[0];
    cFst.rgb *= cFst.a;
    vec4 cLast = u_colors[int(u_colorsCount - 1.)];
    cLast.rgb *= cLast.a;
    gradient = mix(cLast, cFst, localT);
  }

  vec3 color = gradient.rgb * dots;
  float opacity = gradient.a * dots;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1. - opacity);
  opacity = opacity + u_colorBack.a * (1. - opacity);

  fragColor = vec4(color, opacity);
}
`;var zo=`#version 300 es
precision mediump float;

uniform vec4 u_colorBack;
uniform vec4 u_colorFill;
uniform vec4 u_colorStroke;
uniform float u_dotSize;
uniform float u_gapX;
uniform float u_gapY;
uniform float u_strokeWidth;
uniform float u_sizeRange;
uniform float u_opacityRange;
uniform float u_shape;

in vec2 v_patternUV;

out vec4 fragColor;

${P}
${Me}

float polygon(vec2 p, float N, float rot) {
  float a = atan(p.x, p.y) + rot;
  float r = TWO_PI / float(N);

  return cos(floor(.5 + a / r) * r - a) * length(p);
}

void main() {

  // x100 is a default multiplier between vertex and fragmant shaders
  // we use it to avoid UV presision issues
  vec2 shape_uv = 100. * v_patternUV;

  vec2 gap = max(abs(vec2(u_gapX, u_gapY)), vec2(1e-6));
  vec2 grid = fract(shape_uv / gap) + 1e-4;
  vec2 grid_idx = floor(shape_uv / gap);
  float sizeRandomizer = .5 + .8 * snoise(2. * vec2(grid_idx.x * 100., grid_idx.y));
  float opacity_randomizer = .5 + .7 * snoise(2. * vec2(grid_idx.y, grid_idx.x));

  vec2 center = vec2(0.5) - 1e-3;
  vec2 p = (grid - center) * vec2(u_gapX, u_gapY);

  float baseSize = u_dotSize * (1. - sizeRandomizer * u_sizeRange);
  float strokeWidth = u_strokeWidth * (1. - sizeRandomizer * u_sizeRange);

  float dist;
  if (u_shape < 0.5) {
    // Circle
    dist = length(p);
  } else if (u_shape < 1.5) {
    // Diamond
    strokeWidth *= 1.5;
    dist = polygon(1.5 * p, 4., .25 * PI);
  } else if (u_shape < 2.5) {
    // Square
    dist = polygon(1.03 * p, 4., 1e-3);
  } else {
    // Triangle
    strokeWidth *= 1.5;
    p = p * 2. - 1.;
    p *= .9;
    p.y = 1. - p.y;
    p.y -= .75 * baseSize;
    dist = polygon(p, 3., 1e-3);
  }

  float edgeWidth = fwidth(dist);
  float shapeOuter = 1. - smoothstep(baseSize - edgeWidth, baseSize + edgeWidth, dist - strokeWidth);
  float shapeInner = 1. - smoothstep(baseSize - edgeWidth, baseSize + edgeWidth, dist);
  float stroke = shapeOuter - shapeInner;

  float dotOpacity = max(0., 1. - opacity_randomizer * u_opacityRange);
  stroke *= dotOpacity;
  shapeInner *= dotOpacity;

  stroke *= u_colorStroke.a;
  shapeInner *= u_colorFill.a;

  vec3 color = vec3(0.);
  color += stroke * u_colorStroke.rgb;
  color += shapeInner * u_colorFill.rgb;
  color += (1. - shapeInner - stroke) * u_colorBack.rgb * u_colorBack.a;

  float opacity = 0.;
  opacity += stroke;
  opacity += shapeInner;
  opacity += (1. - opacity) * u_colorBack.a;

  fragColor = vec4(color, opacity);
}
`,Oo={circle:0,diamond:1,square:2,triangle:3};var no={maxColorCount:10},Do=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colors[${no.maxColorCount}];
uniform float u_colorsCount;
uniform float u_stepsPerColor;
uniform float u_softness;

in vec2 v_patternUV;

out vec4 fragColor;

${Me}

float getNoise(vec2 uv, float t) {
  float noise = .5 * snoise(uv - vec2(0., .3 * t));
  noise += .5 * snoise(2. * uv + vec2(0., .32 * t));

  return noise;
}

float steppedSmooth(float m, float steps, float softness) {
  float stepT = floor(m * steps) / steps;
  float f = m * steps - floor(m * steps);
  float fw = steps * fwidth(m);
  float smoothed = smoothstep(.5 - softness, min(1., .5 + softness + fw), f);
  return stepT + smoothed / steps;
}

void main() {
  vec2 shape_uv = v_patternUV;
  shape_uv *= .1;

  float t = .2 * u_time;

  float shape = .5 + .5 * getNoise(shape_uv, t);

  float mixer = (shape - .5 / u_colorsCount) * u_colorsCount;

  float steps = max(1., u_stepsPerColor);

  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;
  for (int i = 1; i < ${no.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;

    float localM = clamp(mixer - float(i - 1), 0., 1.);
    localM = steppedSmooth(localM, steps, .5 * u_softness);

    vec4 c = u_colors[i];
    c.rgb *= c.a;
    gradient = mix(gradient, c, localM);
  }

  if ((mixer < 0.) || (mixer > (u_colorsCount - 1.))) {
    float localM = mixer + 1.;
    if (mixer > (u_colorsCount - 1.)) {
      localM = mixer - (u_colorsCount - 1.);
    }
    localM = steppedSmooth(localM, steps, .5 * u_softness);
    vec4 cFst = u_colors[0];
    cFst.rgb *= cFst.a;
    vec4 cLast = u_colors[int(u_colorsCount - 1.)];
    cLast.rgb *= cLast.a;
    gradient = mix(cLast, cFst, localM);
  }

  vec3 color = gradient.rgb;
  float opacity = gradient.a;

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var Ke={maxColorCount:8,maxBallsCount:20},Eo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${Ke.maxColorCount}];
uniform float u_colorsCount;
uniform float u_size;
uniform float u_count;

in vec2 v_objectUV;

out vec4 fragColor;

${P}
${ze}
float noise(float x) {
  float i = floor(x);
  float f = fract(x);
  float u = f * f * (3.0 - 2.0 * f);
  vec2 p0 = vec2(i, 0.0);
  vec2 p1 = vec2(i + 1.0, 0.0);
  return mix(randomR(p0), randomR(p1), u);
}

float getBallShape(vec2 uv, vec2 c, float p) {
  float s = .5 * length(uv - c);
  s = 1. - clamp(s, 0., 1.);
  s = pow(s, p);
  return s;
}

void main() {
  vec2 shape_uv = v_objectUV;

  shape_uv += .5;

  const float firstFrameOffset = 2503.4;
  float t = .2 * (u_time + firstFrameOffset);

  vec3 totalColor = vec3(0.);
  float totalShape = 0.;
  float totalOpacity = 0.;

  for (int i = 0; i < ${Ke.maxBallsCount}; i++) {
    if (i >= int(ceil(u_count))) break;

    float idxFract = float(i) / float(${Ke.maxBallsCount});
    float angle = TWO_PI * idxFract;

    float speed = 1. - .2 * idxFract;
    float noiseX = noise(angle * 10. + float(i) + t * speed);
    float noiseY = noise(angle * 20. + float(i) - t * speed);

    vec2 pos = vec2(.5) + 1e-4 + .9 * (vec2(noiseX, noiseY) - .5);

    int safeIndex = i % int(u_colorsCount + 0.5);
    vec4 ballColor = u_colors[safeIndex];
    ballColor.rgb *= ballColor.a;

    float sizeFrac = 1.;
    if (float(i) > floor(u_count - 1.)) {
      sizeFrac *= fract(u_count);
    }

    float shape = getBallShape(shape_uv, pos, 45. - 30. * u_size * sizeFrac);
    shape *= pow(u_size, .2);
    shape = smoothstep(0., 1., shape);

    totalColor += ballColor.rgb * shape;
    totalShape += shape;
    totalOpacity += ballColor.a * shape;
  }

  totalColor /= max(totalShape, 1e-4);
  totalOpacity /= max(totalShape, 1e-4);

  float edge_width = fwidth(totalShape);
  float finalShape = smoothstep(.4, .4 + edge_width, totalShape);

  vec3 color = totalColor * finalShape;
  float opacity = totalOpacity * finalShape;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1. - opacity);
  opacity = opacity + u_colorBack.a * (1. - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var Go=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colorFront;
uniform vec4 u_colorBack;
uniform float u_proportion;
uniform float u_softness;
uniform float u_octaveCount;
uniform float u_persistence;
uniform float u_lacunarity;

in vec2 v_patternUV;

out vec4 fragColor;

${P}
${Ge}
${me}

float hash31(vec3 p) {
  p = fract(p * 0.3183099) + 0.1;
  p += dot(p, p.yzx + 19.19);
  return fract(p.x * (p.y + p.z));
}

vec3 gradientPredefined(float hash) {
  int idx = int(hash * 12.0) % 12;

  if (idx == 0) return vec3(1, 1, 0);
  if (idx == 1) return vec3(-1, 1, 0);
  if (idx == 2) return vec3(1, -1, 0);
  if (idx == 3) return vec3(-1, -1, 0);
  if (idx == 4) return vec3(1, 0, 1);
  if (idx == 5) return vec3(-1, 0, 1);
  if (idx == 6) return vec3(1, 0, -1);
  if (idx == 7) return vec3(-1, 0, -1);
  if (idx == 8) return vec3(0, 1, 1);
  if (idx == 9) return vec3(0, -1, 1);
  if (idx == 10) return vec3(0, 1, -1);
  return vec3(0, -1, -1);// idx == 11
}

float interpolateSafe(float v000, float v001, float v010, float v011,
float v100, float v101, float v110, float v111, vec3 t) {
  t = clamp(t, 0.0, 1.0);

  float v00 = mix(v000, v100, t.x);
  float v01 = mix(v001, v101, t.x);
  float v10 = mix(v010, v110, t.x);
  float v11 = mix(v011, v111, t.x);

  float v0 = mix(v00, v10, t.y);
  float v1 = mix(v01, v11, t.y);

  return mix(v0, v1, t.z);
}

vec3 fade(vec3 t) {
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

float perlinNoise(vec3 position, float seed) {
  position += vec3(seed * 127.1, seed * 311.7, seed * 74.7);

  vec3 i = floor(position);
  vec3 f = fract(position);
  float h000 = hash31(i);
  float h001 = hash31(i + vec3(0, 0, 1));
  float h010 = hash31(i + vec3(0, 1, 0));
  float h011 = hash31(i + vec3(0, 1, 1));
  float h100 = hash31(i + vec3(1, 0, 0));
  float h101 = hash31(i + vec3(1, 0, 1));
  float h110 = hash31(i + vec3(1, 1, 0));
  float h111 = hash31(i + vec3(1, 1, 1));
  vec3 g000 = gradientPredefined(h000);
  vec3 g001 = gradientPredefined(h001);
  vec3 g010 = gradientPredefined(h010);
  vec3 g011 = gradientPredefined(h011);
  vec3 g100 = gradientPredefined(h100);
  vec3 g101 = gradientPredefined(h101);
  vec3 g110 = gradientPredefined(h110);
  vec3 g111 = gradientPredefined(h111);
  float v000 = dot(g000, f - vec3(0, 0, 0));
  float v001 = dot(g001, f - vec3(0, 0, 1));
  float v010 = dot(g010, f - vec3(0, 1, 0));
  float v011 = dot(g011, f - vec3(0, 1, 1));
  float v100 = dot(g100, f - vec3(1, 0, 0));
  float v101 = dot(g101, f - vec3(1, 0, 1));
  float v110 = dot(g110, f - vec3(1, 1, 0));
  float v111 = dot(g111, f - vec3(1, 1, 1));

  vec3 u = fade(f);
  return interpolateSafe(v000, v001, v010, v011, v100, v101, v110, v111, u);
}

float p_noise(vec3 position, int octaveCount, float persistence, float lacunarity) {
  float value = 0.0;
  float amplitude = 1.0;
  float frequency = 10.0;
  octaveCount = clamp(octaveCount, 1, 8);

  for (int i = 0; i < octaveCount; i++) {
    float seed = float(i) * 0.7319;
    value += perlinNoise(position * frequency, seed) * amplitude;
    amplitude *= persistence;
    frequency *= lacunarity;
  }
  return value;
}

float get_max_amp(float persistence, float octaveCount) {
  persistence = clamp(persistence * 0.999, 0.0, 0.999);
  octaveCount = clamp(octaveCount, 1.0, 8.0);

  return (1.0 - pow(persistence, octaveCount)) / max(1e-4, (1.0 - persistence));
}

void main() {
  vec2 uv = v_patternUV;
  uv *= .5;

  float t = .2 * u_time;

  vec3 p = vec3(uv, t);

  float octCount = floor(u_octaveCount);
  float noise = p_noise(p, int(octCount), u_persistence, u_lacunarity);

  float max_amp = get_max_amp(u_persistence, octCount);
  float noise_normalized = clamp((noise + max_amp) / max(1e-4, (2. * max_amp)) + (u_proportion - .5), 0.0, 1.0);
  float sharpness = clamp(u_softness, 0., 1.);
  float smooth_w = 0.5 * max(fwidth(noise_normalized), 0.001);
  float res = smoothstep(
  .5 - .5 * sharpness - smooth_w,
  .5 + .5 * sharpness + smooth_w,
  noise_normalized
  );

  vec3 fgColor = u_colorFront.rgb * u_colorFront.a;
  float fgOpacity = u_colorFront.a;
  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  float bgOpacity = u_colorBack.a;

  vec3 color = fgColor * res;
  float opacity = fgOpacity * res;

  color += bgColor * (1. - opacity);
  opacity += bgOpacity * (1. - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var lo={maxColorCount:5},Yo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform float u_scale;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colors[${lo.maxColorCount}];
uniform float u_colorsCount;

uniform float u_stepsPerColor;
uniform vec4 u_colorGlow;
uniform vec4 u_colorGap;
uniform float u_distortion;
uniform float u_gap;
uniform float u_glow;

in vec2 v_patternUV;

out vec4 fragColor;

${P}
${qe}

vec4 voronoi(vec2 x, float t) {
  vec2 ip = floor(x);
  vec2 fp = fract(x);

  vec2 mg, mr;
  float md = 8.;
  float rand = 0.;

  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec2 g = vec2(float(i), float(j));
      vec2 o = randomGB(ip + g);
      float raw_hash = o.x;
      o = .5 + u_distortion * sin(t + TWO_PI * o);
      vec2 r = g + o - fp;
      float d = dot(r, r);

      if (d < md) {
        md = d;
        mr = r;
        mg = g;
        rand = raw_hash;
      }
    }
  }

  md = 8.;
  for (int j = -2; j <= 2; j++) {
    for (int i = -2; i <= 2; i++) {
      vec2 g = mg + vec2(float(i), float(j));
      vec2 o = randomGB(ip + g);
      o = .5 + u_distortion * sin(t + TWO_PI * o);
      vec2 r = g + o - fp;
      if (dot(mr - r, mr - r) > .00001) {
        md = min(md, dot(.5 * (mr + r), normalize(r - mr)));
      }
    }
  }

  return vec4(md, mr, rand);
}

void main() {
  vec2 shape_uv = v_patternUV;
  shape_uv *= 1.25;

  float t = u_time;

  vec4 voronoiRes = voronoi(shape_uv, t);

  float shape = clamp(voronoiRes.w, 0., 1.);
  float mixer = shape * (u_colorsCount - 1.);
  mixer = (shape - .5 / u_colorsCount) * u_colorsCount;
  float steps = max(1., u_stepsPerColor);

  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;
  for (int i = 1; i < ${lo.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;
    float localT = clamp(mixer - float(i - 1), 0.0, 1.0);
    localT = round(localT * steps) / steps;
    vec4 c = u_colors[i];
    c.rgb *= c.a;
    gradient = mix(gradient, c, localT);
  }

  if ((mixer < 0.) || (mixer > (u_colorsCount - 1.))) {
    float localT = mixer + 1.;
    if (mixer > (u_colorsCount - 1.)) {
      localT = mixer - (u_colorsCount - 1.);
    }
    localT = round(localT * steps) / steps;
    vec4 cFst = u_colors[0];
    cFst.rgb *= cFst.a;
    vec4 cLast = u_colors[int(u_colorsCount - 1.)];
    cLast.rgb *= cLast.a;
    gradient = mix(cLast, cFst, localT);
  }

  vec3 cellColor = gradient.rgb;
  float cellOpacity = gradient.a;

  float glows = length(voronoiRes.yz * u_glow);
  glows = pow(glows, 1.5);

  vec3 color = mix(cellColor, u_colorGlow.rgb * u_colorGlow.a, u_colorGlow.a * glows);
  float opacity = cellOpacity + u_colorGlow.a * glows;

  float edge = voronoiRes.x;
  float smoothEdge = .02 / (2. * u_scale) * (1. + .5 * u_gap);
  edge = smoothstep(u_gap - smoothEdge, u_gap + smoothEdge, edge);

  color = mix(u_colorGap.rgb * u_colorGap.a, color, edge);
  opacity = mix(u_colorGap.a, opacity, edge);

  fragColor = vec4(color, opacity);
}
`;var To=`#version 300 es
precision mediump float;

uniform vec4 u_colorFront;
uniform vec4 u_colorBack;
uniform float u_shape;
uniform float u_frequency;
uniform float u_amplitude;
uniform float u_spacing;
uniform float u_proportion;
uniform float u_softness;

in vec2 v_patternUV;

out vec4 fragColor;

${P}

void main() {
  vec2 shape_uv = v_patternUV;
  shape_uv *= 4.;

  float wave = .5 * cos(shape_uv.x * u_frequency * TWO_PI);
  float zigzag = 2. * abs(fract(shape_uv.x * u_frequency) - .5);
  float irregular = sin(shape_uv.x * .25 * u_frequency * TWO_PI) * cos(shape_uv.x * u_frequency * TWO_PI);
  float irregular2 = .75 * (sin(shape_uv.x * u_frequency * TWO_PI) + .5 * cos(shape_uv.x * .5 * u_frequency * TWO_PI));

  float offset = mix(zigzag, wave, smoothstep(0., 1., u_shape));
  offset = mix(offset, irregular, smoothstep(1., 2., u_shape));
  offset = mix(offset, irregular2, smoothstep(2., 3., u_shape));
  offset *= 2. * u_amplitude;

  float spacing = (.001 + u_spacing);
  float shape = .5 + .5 * sin((shape_uv.y + offset) * PI / spacing);

  float aa = .0001 + fwidth(shape);
  float dc = 1. - clamp(u_proportion, 0., 1.);
  float e0 = dc - u_softness - aa;
  float e1 = dc + u_softness + aa;
  float res = smoothstep(min(e0, e1), max(e0, e1), shape);

  vec3 fgColor = u_colorFront.rgb * u_colorFront.a;
  float fgOpacity = u_colorFront.a;
  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  float bgOpacity = u_colorBack.a;

  vec3 color = fgColor * res;
  float opacity = fgOpacity * res;

  color += bgColor * (1. - opacity);
  opacity += bgOpacity * (1. - opacity);

  fragColor = vec4(color, opacity);
}
`;var co={maxColorCount:10},Wo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colors[${co.maxColorCount}];
uniform float u_colorsCount;
uniform float u_proportion;
uniform float u_softness;
uniform float u_shape;
uniform float u_shapeScale;
uniform float u_distortion;
uniform float u_swirl;
uniform float u_swirlIterations;

in vec2 v_patternUV;

out vec4 fragColor;

${P}
${L}
float randomG(vec2 p) {
  vec2 uv = floor(p) / 100. + .5;
  return texture(u_noiseTexture, fract(uv)).g;
}
float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = randomG(i);
  float b = randomG(i + vec2(1.0, 0.0));
  float c = randomG(i + vec2(0.0, 1.0));
  float d = randomG(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}


void main() {
  vec2 uv = v_patternUV;
  uv *= .5;

  const float firstFrameOffset = 118.;
  float t = 0.0625 * (u_time + firstFrameOffset);

  float n1 = valueNoise(uv * 1. + t);
  float n2 = valueNoise(uv * 2. - t);
  float angle = n1 * TWO_PI;
  uv.x += 4. * u_distortion * n2 * cos(angle);
  uv.y += 4. * u_distortion * n2 * sin(angle);

  float swirl = u_swirl;
  for (int i = 1; i <= 20; i++) {
    if (i >= int(u_swirlIterations)) break;
    float iFloat = float(i);
    uv.x += swirl / iFloat * cos(t + iFloat * 1.5 * uv.y);
    uv.y += swirl / iFloat * cos(t + iFloat * 1. * uv.x);
  }

  float proportion = clamp(u_proportion, 0., 1.);

  float shape = 0.;
  if (u_shape < .5) {
    vec2 checksShape_uv = uv * (.5 + 3.5 * u_shapeScale);
    shape = .5 + .5 * sin(checksShape_uv.x) * cos(checksShape_uv.y);
    shape += .48 * sign(proportion - .5) * pow(abs(proportion - .5), .5);
  } else if (u_shape < 1.5) {
    vec2 stripesShape_uv = uv * (2. * u_shapeScale);
    float f = fract(stripesShape_uv.y);
    shape = smoothstep(.0, .55, f) * (1.0 - smoothstep(.45, 1., f));
    shape += .48 * sign(proportion - .5) * pow(abs(proportion - .5), .5);
  } else {
    float shapeScaling = 5. * (1. - u_shapeScale);
    float e0 = 0.45 - shapeScaling;
    float e1 = 0.55 + shapeScaling;
    shape = smoothstep(min(e0, e1), max(e0, e1), 1.0 - uv.y + 0.3 * (proportion - 0.5));
  }

  float mixer = shape * (u_colorsCount - 1.);
  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;
  float aa = fwidth(shape);
  for (int i = 1; i < ${co.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;
    float m = clamp(mixer - float(i - 1), 0.0, 1.0);

    float localMixerStart = floor(m);
    float softness = .5 * u_softness + fwidth(m);
    float smoothed = smoothstep(max(0., .5 - softness - aa), min(1., .5 + softness + aa), m - localMixerStart);
    float stepped = localMixerStart + smoothed;

    m = mix(stepped, m, u_softness);

    vec4 c = u_colors[i];
    c.rgb *= c.a;
    gradient = mix(gradient, c, m);
  }

  vec3 color = gradient.rgb;
  float opacity = gradient.a;

  ${Z}

  fragColor = vec4(color, opacity);
}
`,No={checks:0,stripes:1,edge:2};var fo={maxColorCount:5},Qo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colorBack;
uniform vec4 u_colorBloom;
uniform vec4 u_colors[${fo.maxColorCount}];
uniform float u_colorsCount;

uniform float u_density;
uniform float u_spotty;
uniform float u_midSize;
uniform float u_midIntensity;
uniform float u_intensity;
uniform float u_bloom;

in vec2 v_objectUV;

out vec4 fragColor;

${P}
${L}
${ze}
float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = randomR(i);
  float b = randomR(i + vec2(1.0, 0.0));
  float c = randomR(i + vec2(0.0, 1.0));
  float d = randomR(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

${Ge}

float raysShape(vec2 uv, float r, float freq, float intensity, float radius) {
  float a = atan(uv.y, uv.x);
  vec2 left = vec2(a * freq, r);
  vec2 right = vec2(fract(a / TWO_PI) * TWO_PI * freq, r);
  float n_left = pow(valueNoise(left), intensity);
  float n_right = pow(valueNoise(right), intensity);
  float shape = mix(n_right, n_left, smoothstep(-.15, .15, uv.x));
  return shape;
}

void main() {
  vec2 shape_uv = v_objectUV;

  float t = .2 * u_time;

  float radius = length(shape_uv);
  float spots = 6.5 * abs(u_spotty);

  float intensity = 4. - 3. * clamp(u_intensity, 0., 1.);

  float delta = 1. - smoothstep(0., 1., radius);

  float midSize = 10. * abs(u_midSize);
  float ms_lo = 0.02 * midSize;
  float ms_hi = max(midSize, 1e-6);
  float middleShape = pow(u_midIntensity, 0.3) * (1. - smoothstep(ms_lo, ms_hi, 3.0 * radius));
  middleShape = pow(middleShape, 5.0);

  vec3 accumColor = vec3(0.0);
  float accumAlpha = 0.0;

  for (int i = 0; i < ${fo.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;

    vec2 rotatedUV = rotate(shape_uv, float(i) + 1.0);

    float r1 = radius * (1.0 + 0.4 * float(i)) - 3.0 * t;
    float r2 = 0.5 * radius * (1.0 + spots) - 2.0 * t;
    float density = 6. * u_density + step(.5, u_density) * pow(4.5 * (u_density - .5), 4.);
    float f = mix(1.0, 3.0 + 0.5 * float(i), hash11(float(i) * 15.)) * density;

    float ray = raysShape(rotatedUV, r1, 5.0 * f, intensity, radius);
    ray *= raysShape(rotatedUV, r2, 4.0 * f, intensity, radius);
    ray += (1. + 4. * ray) * middleShape;
    ray = clamp(ray, 0.0, 1.0);

    float srcAlpha = u_colors[i].a * ray;
    vec3 srcColor = u_colors[i].rgb * srcAlpha;

    vec3 alphaBlendColor = accumColor + (1.0 - accumAlpha) * srcColor;
    float alphaBlendAlpha = accumAlpha + (1.0 - accumAlpha) * srcAlpha;

    vec3 addBlendColor = accumColor + srcColor;
    float addBlendAlpha = accumAlpha + srcAlpha;

    accumColor = mix(alphaBlendColor, addBlendColor, u_bloom);
    accumAlpha = mix(alphaBlendAlpha, addBlendAlpha, u_bloom);
  }

  float overlayAlpha = u_colorBloom.a;
  vec3 overlayColor = u_colorBloom.rgb * overlayAlpha;

  vec3 colorWithOverlay = accumColor + accumAlpha * overlayColor;
  accumColor = mix(accumColor, colorWithOverlay, u_bloom);

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;

  vec3 color = accumColor + (1. - accumAlpha) * bgColor;
  float opacity = accumAlpha + (1. - accumAlpha) * u_colorBack.a;
  color = clamp(color, 0., 1.);
  opacity = clamp(opacity, 0., 1.);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var Lo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colorBack;
uniform vec4 u_colorFront;
uniform float u_density;
uniform float u_distortion;
uniform float u_strokeWidth;
uniform float u_strokeCap;
uniform float u_strokeTaper;
uniform float u_noise;
uniform float u_noiseFrequency;
uniform float u_softness;

in vec2 v_patternUV;

out vec4 fragColor;

${P}
${Me}

void main() {
  vec2 uv = 2. * v_patternUV;

  float t = u_time;
  float l = length(uv);
  float density = clamp(u_density, 0., 1.);
  l = pow(max(l, 1e-6), density);
  float angle = atan(uv.y, uv.x) - t;
  float angleNormalised = angle / TWO_PI;

  if (u_noise > 0.) {
    angleNormalised += .125 * u_noise * snoise(16. * pow(u_noiseFrequency, 3.) * uv);
  }

  float offset = l + angleNormalised;
  offset -= u_distortion * (sin(4. * l - .5 * t) * cos(PI + l + .5 * t));
  float stripe = fract(offset);

  float shape = 2. * abs(stripe - .5);
  float width = 1. - clamp(u_strokeWidth, .005 * u_strokeTaper, 1.);


  float wCap = mix(width, (1. - stripe) * (1. - step(.5, stripe)), (1. - clamp(l, 0., 1.)));
  width = mix(width, wCap, u_strokeCap);
  width *= (1. - clamp(u_strokeTaper, 0., 1.) * l);

  float fw = fwidth(offset);
  float fwMult = 4. - 3. * (smoothstep(.05, .4, 2. * u_strokeWidth) * smoothstep(.05, .4, 2. * (1. - u_strokeWidth)));
  float pixelSize = mix(fwMult * fw, fwidth(shape), clamp(fw, 0., 1.));
  pixelSize = mix(pixelSize, .002, u_strokeCap * (1. - clamp(l, 0., 1.)));

  float res = smoothstep(width - pixelSize - u_softness, width + pixelSize + u_softness, shape);

  vec3 fgColor = u_colorFront.rgb * u_colorFront.a;
  float fgOpacity = u_colorFront.a;
  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  float bgOpacity = u_colorBack.a;

  vec3 color = fgColor * res;
  float opacity = fgOpacity * res;

  color += bgColor * (1. - opacity);
  opacity += bgOpacity * (1. - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var uo={maxColorCount:10},Ho=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${uo.maxColorCount}];
uniform float u_colorsCount;
uniform float u_bandCount;
uniform float u_twist;
uniform float u_center;
uniform float u_proportion;
uniform float u_softness;
uniform float u_noise;
uniform float u_noiseFrequency;

in vec2 v_objectUV;

out vec4 fragColor;

${P}
${Me}
${L}

void main() {
  vec2 shape_uv = v_objectUV;

  float l = length(shape_uv);
  l = max(1e-4, l);

  float t = u_time;

  float angle = ceil(u_bandCount) * atan(shape_uv.y, shape_uv.x) + t;
  float angle_norm = angle / TWO_PI;

  float twist = 3. * clamp(u_twist, 0., 1.);
  float offset = pow(l, -twist) + angle_norm;

  float shape = fract(offset);
  shape = 1. - abs(2. * shape - 1.);
  if (u_noise > 0.) {
    shape += u_noise * snoise(15. * pow(u_noiseFrequency, 2.) * shape_uv);
  }

  float mid = smoothstep(.2, .2 + .8 * u_center, pow(l, twist));
  shape = mix(0., shape, mid);

  float proportion = clamp(u_proportion, 0., 1.);
  float exponent = mix(.25, 1., proportion * 2.);
  exponent = mix(exponent, 10., max(0., proportion * 2. - 1.));
  shape = pow(shape, exponent);

  float mixer = shape * u_colorsCount;
  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;

  float outerShape = 0.;
  for (int i = 1; i < ${uo.maxColorCount+1}; i++) {
    if (i > int(u_colorsCount)) break;

    float m = clamp(mixer - float(i - 1), 0., 1.);
    float aa = fwidth(m);
    m = smoothstep(.5 - .5 * u_softness - aa, .5 + .5 * u_softness + aa, m);

    if (i == 1) {
      outerShape = m;
    }

    vec4 c = u_colors[i - 1];
    c.rgb *= c.a;
    gradient = mix(gradient, c, m);
  }

  float midAA = .1 * fwidth(pow(l, -twist));
  float outerMid = smoothstep(.2, .2 + midAA, pow(l, twist));
  outerShape = mix(0., outerShape, outerMid);

  vec3 color = gradient.rgb * outerShape;
  float opacity = gradient.a * outerShape;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1.0 - opacity);
  opacity = opacity + u_colorBack.a * (1.0 - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var Xo=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec2 u_resolution;
uniform float u_pixelRatio;
uniform float u_originX;
uniform float u_originY;
uniform float u_worldWidth;
uniform float u_worldHeight;
uniform float u_fit;
uniform float u_scale;
uniform float u_rotation;
uniform float u_offsetX;
uniform float u_offsetY;

uniform float u_pxSize;
uniform vec4 u_colorBack;
uniform vec4 u_colorFront;
uniform float u_shape;
uniform float u_type;

out vec4 fragColor;

${Me}
${P}
${Ge}
${me}

float getSimplexNoise(vec2 uv, float t) {
  float noise = .5 * snoise(uv - vec2(0., .3 * t));
  noise += .5 * snoise(2. * uv + vec2(0., .32 * t));

  return noise;
}

const int bayer2x2[4] = int[4](0, 2, 3, 1);
const int bayer4x4[16] = int[16](
0, 8, 2, 10,
12, 4, 14, 6,
3, 11, 1, 9,
15, 7, 13, 5
);

const int bayer8x8[64] = int[64](
0, 32, 8, 40, 2, 34, 10, 42,
48, 16, 56, 24, 50, 18, 58, 26,
12, 44, 4, 36, 14, 46, 6, 38,
60, 28, 52, 20, 62, 30, 54, 22,
3, 35, 11, 43, 1, 33, 9, 41,
51, 19, 59, 27, 49, 17, 57, 25,
15, 47, 7, 39, 13, 45, 5, 37,
63, 31, 55, 23, 61, 29, 53, 21
);

float getBayerValue(vec2 uv, int size) {
  ivec2 pos = ivec2(fract(uv / float(size)) * float(size));
  int index = pos.y * size + pos.x;

  if (size == 2) {
    return float(bayer2x2[index]) / 4.0;
  } else if (size == 4) {
    return float(bayer4x4[index]) / 16.0;
  } else if (size == 8) {
    return float(bayer8x8[index]) / 64.0;
  }
  return 0.0;
}


void main() {
  float t = .5 * u_time;

  float pxSize = u_pxSize * u_pixelRatio;
  vec2 pxSizeUV = gl_FragCoord.xy - .5 * u_resolution;
  pxSizeUV /= pxSize;
  vec2 canvasPixelizedUV = (floor(pxSizeUV) + .5) * pxSize;
  vec2 normalizedUV = canvasPixelizedUV / u_resolution;

  vec2 ditheringNoiseUV = canvasPixelizedUV;
  vec2 shapeUV = normalizedUV;

  vec2 boxOrigin = vec2(.5 - u_originX, u_originY - .5);
  vec2 givenBoxSize = vec2(u_worldWidth, u_worldHeight);
  givenBoxSize = max(givenBoxSize, vec2(1.)) * u_pixelRatio;
  float r = u_rotation * PI / 180.;
  mat2 graphicRotation = mat2(cos(r), sin(r), -sin(r), cos(r));
  vec2 graphicOffset = vec2(-u_offsetX, u_offsetY);

  float patternBoxRatio = givenBoxSize.x / givenBoxSize.y;
  vec2 boxSize = vec2(
  (u_worldWidth == 0.) ? u_resolution.x : givenBoxSize.x,
  (u_worldHeight == 0.) ? u_resolution.y : givenBoxSize.y
  );
  
  if (u_shape > 3.5) {
    vec2 objectBoxSize = vec2(0.);
    // fit = none
    objectBoxSize.x = min(boxSize.x, boxSize.y);
    if (u_fit == 1.) { // fit = contain
      objectBoxSize.x = min(u_resolution.x, u_resolution.y);
    } else if (u_fit == 2.) { // fit = cover
      objectBoxSize.x = max(u_resolution.x, u_resolution.y);
    }
    objectBoxSize.y = objectBoxSize.x;
    vec2 objectWorldScale = u_resolution.xy / objectBoxSize;

    shapeUV *= objectWorldScale;
    shapeUV += boxOrigin * (objectWorldScale - 1.);
    shapeUV += vec2(-u_offsetX, u_offsetY);
    shapeUV /= u_scale;
    shapeUV = graphicRotation * shapeUV;
  } else {
    vec2 patternBoxSize = vec2(0.);
    // fit = none
    patternBoxSize.x = patternBoxRatio * min(boxSize.x / patternBoxRatio, boxSize.y);
    float patternWorldNoFitBoxWidth = patternBoxSize.x;
    if (u_fit == 1.) { // fit = contain
      patternBoxSize.x = patternBoxRatio * min(u_resolution.x / patternBoxRatio, u_resolution.y);
    } else if (u_fit == 2.) { // fit = cover
      patternBoxSize.x = patternBoxRatio * max(u_resolution.x / patternBoxRatio, u_resolution.y);
    }
    patternBoxSize.y = patternBoxSize.x / patternBoxRatio;
    vec2 patternWorldScale = u_resolution.xy / patternBoxSize;

    shapeUV += vec2(-u_offsetX, u_offsetY) / patternWorldScale;
    shapeUV += boxOrigin;
    shapeUV -= boxOrigin / patternWorldScale;
    shapeUV *= u_resolution.xy;
    shapeUV /= u_pixelRatio;
    if (u_fit > 0.) {
      shapeUV *= (patternWorldNoFitBoxWidth / patternBoxSize.x);
    }
    shapeUV /= u_scale;
    shapeUV = graphicRotation * shapeUV;
    shapeUV += boxOrigin / patternWorldScale;
    shapeUV -= boxOrigin;
    shapeUV += .5;
  }

  float shape = 0.;
  if (u_shape < 1.5) {
    // Simplex noise
    shapeUV *= .001;

    shape = 0.5 + 0.5 * getSimplexNoise(shapeUV, t);
    shape = smoothstep(0.3, 0.9, shape);

  } else if (u_shape < 2.5) {
    // Warp
    shapeUV *= .003;

    for (float i = 1.0; i < 6.0; i++) {
      shapeUV.x += 0.6 / i * cos(i * 2.5 * shapeUV.y + t);
      shapeUV.y += 0.6 / i * cos(i * 1.5 * shapeUV.x + t);
    }

    shape = .15 / max(0.001, abs(sin(t - shapeUV.y - shapeUV.x)));
    shape = smoothstep(0.02, 1., shape);

  } else if (u_shape < 3.5) {
    // Dots
    shapeUV *= .05;

    float stripeIdx = floor(2. * shapeUV.x / TWO_PI);
    float rand = hash11(stripeIdx * 10.);
    rand = sign(rand - .5) * pow(.1 + abs(rand), .4);
    shape = sin(shapeUV.x) * cos(shapeUV.y - 5. * rand * t);
    shape = pow(abs(shape), 6.);

  } else if (u_shape < 4.5) {
    // Sine wave
    shapeUV *= 4.;

    float wave = cos(.5 * shapeUV.x - 2. * t) * sin(1.5 * shapeUV.x + t) * (.75 + .25 * cos(3. * t));
    shape = 1. - smoothstep(-1., 1., shapeUV.y + wave);

  } else if (u_shape < 5.5) {
    // Ripple

    float dist = length(shapeUV);
    float waves = sin(pow(dist, 1.7) * 7. - 3. * t) * .5 + .5;
    shape = waves;

  } else if (u_shape < 6.5) {
    // Swirl

    float l = length(shapeUV);
    float angle = 6. * atan(shapeUV.y, shapeUV.x) + 4. * t;
    float twist = 1.2;
    float offset = 1. / pow(max(l, 1e-6), twist) + angle / TWO_PI;
    float mid = smoothstep(0., 1., pow(l, twist));
    shape = mix(0., fract(offset), mid);

  } else {
    // Sphere
    shapeUV *= 2.;

    float d = 1. - pow(length(shapeUV), 2.);
    vec3 pos = vec3(shapeUV, sqrt(max(0., d)));
    vec3 lightPos = normalize(vec3(cos(1.5 * t), .8, sin(1.25 * t)));
    shape = .5 + .5 * dot(lightPos, pos);
    shape *= step(0., d);
  }


  int type = int(floor(u_type));
  float dithering = 0.0;

  switch (type) {
    case 1: {
      dithering = step(hash21(ditheringNoiseUV), shape);
    } break;
    case 2:
    dithering = getBayerValue(pxSizeUV, 2);
    break;
    case 3:
    dithering = getBayerValue(pxSizeUV, 4);
    break;
    default :
    dithering = getBayerValue(pxSizeUV, 8);
    break;
  }

  dithering -= .5;
  float res = step(.5, shape + dithering);

  vec3 fgColor = u_colorFront.rgb * u_colorFront.a;
  float fgOpacity = u_colorFront.a;
  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  float bgOpacity = u_colorBack.a;

  vec3 color = fgColor * res;
  float opacity = fgOpacity * res;

  color += bgColor * (1. - opacity);
  opacity += bgOpacity * (1. - opacity);

  fragColor = vec4(color, opacity);
}
`,qo={simplex:1,warp:2,dots:3,wave:4,ripple:5,swirl:6,sphere:7},mo={random:1,"2x2":2,"4x4":3,"8x8":4};var po={maxColorCount:7},jo=`#version 300 es
precision lowp float;

uniform mediump float u_time;
uniform mediump vec2 u_resolution;
uniform mediump float u_pixelRatio;

uniform sampler2D u_noiseTexture;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${po.maxColorCount}];
uniform float u_colorsCount;
uniform float u_softness;
uniform float u_intensity;
uniform float u_noise;
uniform float u_shape;

uniform mediump float u_worldWidth;
uniform mediump float u_worldHeight;
uniform mediump float u_fit;

uniform mediump float u_scale;
uniform mediump float u_rotation;
uniform mediump float u_offsetX;
uniform mediump float u_offsetY;

in vec2 v_objectUV;
in vec2 v_patternUV;
in vec2 v_objectBoxSize;
in vec2 v_patternBoxSize;

out vec4 fragColor;

${P}
${Me}
${L}
${ze}

float valueNoiseR(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = randomR(i);
  float b = randomR(i + vec2(1.0, 0.0));
  float c = randomR(i + vec2(0.0, 1.0));
  float d = randomR(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}
vec4 fbmR(vec2 n0, vec2 n1, vec2 n2, vec2 n3) {
  float amplitude = 0.2;
  vec4 total = vec4(0.);
  for (int i = 0; i < 3; i++) {
    n0 = rotate(n0, 0.3);
    n1 = rotate(n1, 0.3);
    n2 = rotate(n2, 0.3);
    n3 = rotate(n3, 0.3);
    total.x += valueNoiseR(n0) * amplitude;
    total.y += valueNoiseR(n1) * amplitude;
    total.z += valueNoiseR(n2) * amplitude;
    total.z += valueNoiseR(n3) * amplitude;
    n0 *= 1.99;
    n1 *= 1.99;
    n2 *= 1.99;
    n3 *= 1.99;
    amplitude *= 0.6;
  }
  return total;
}

${Ge}

vec2 truchet(vec2 uv, float idx){
  idx = fract(((idx - .5) * 2.));
  if (idx > 0.75) {
    uv = vec2(1.0) - uv;
  } else if (idx > 0.5) {
    uv = vec2(1.0 - uv.x, uv.y);
  } else if (idx > 0.25) {
    uv = 1.0 - vec2(1.0 - uv.x, uv.y);
  }
  return uv;
}

void main() {

  const float firstFrameOffset = 7.;
  float t = .1 * (u_time + firstFrameOffset);

  vec2 shape_uv = vec2(0.);
  vec2 grain_uv = vec2(0.);

  float r = u_rotation * PI / 180.;
  float cr = cos(r);
  float sr = sin(r);
  mat2 graphicRotation = mat2(cr, sr, -sr, cr);
  vec2 graphicOffset = vec2(-u_offsetX, u_offsetY);

  if (u_shape > 3.5) {
    shape_uv = v_objectUV;
    grain_uv = shape_uv;

    // apply inverse transform to grain_uv so it respects the originXY
    grain_uv = transpose(graphicRotation) * grain_uv;
    grain_uv *= u_scale;
    grain_uv -= graphicOffset;
    grain_uv *= v_objectBoxSize;
    grain_uv *= .7;
  } else {
    shape_uv = .5 * v_patternUV;
    grain_uv = 100. * v_patternUV;

    // apply inverse transform to grain_uv so it respects the originXY
    grain_uv = transpose(graphicRotation) * grain_uv;
    grain_uv *= u_scale;
    if (u_fit > 0.) {
      vec2 givenBoxSize = vec2(u_worldWidth, u_worldHeight);
      givenBoxSize = max(givenBoxSize, vec2(1.)) * u_pixelRatio;
      float patternBoxRatio = givenBoxSize.x / givenBoxSize.y;
      vec2 patternBoxGivenSize = vec2(
      (u_worldWidth == 0.) ? u_resolution.x : givenBoxSize.x,
      (u_worldHeight == 0.) ? u_resolution.y : givenBoxSize.y
      );
      patternBoxRatio = patternBoxGivenSize.x / patternBoxGivenSize.y;
      float patternBoxNoFitBoxWidth = patternBoxRatio * min(patternBoxGivenSize.x / patternBoxRatio, patternBoxGivenSize.y);
      grain_uv /= (patternBoxNoFitBoxWidth / v_patternBoxSize.x);
    }
    vec2 patternBoxScale = u_resolution.xy / v_patternBoxSize;
    grain_uv -= graphicOffset / patternBoxScale;
    grain_uv *= 1.6;
  }


  float shape = 0.;

  if (u_shape < 1.5) {
    // Sine wave

    float wave = cos(.5 * shape_uv.x - 4. * t) * sin(1.5 * shape_uv.x + 2. * t) * (.75 + .25 * cos(6. * t));
    shape = 1. - smoothstep(-1., 1., shape_uv.y + wave);

  } else if (u_shape < 2.5) {
    // Grid (dots)

    float stripeIdx = floor(2. * shape_uv.x / TWO_PI);
    float rand = hash11(stripeIdx * 100.);
    rand = sign(rand - .5) * pow(4. * abs(rand), .3);
    shape = sin(shape_uv.x) * cos(shape_uv.y - 5. * rand * t);
    shape = pow(abs(shape), 4.);

  } else if (u_shape < 3.5) {
    // Truchet pattern

    float n2 = valueNoiseR(shape_uv * .4 - 3.75 * t);
    shape_uv.x += 10.;
    shape_uv *= .6;

    vec2 tile = truchet(fract(shape_uv), randomR(floor(shape_uv)));

    float distance1 = length(tile);
    float distance2 = length(tile - vec2(1.));

    n2 -= .5;
    n2 *= .1;
    shape = smoothstep(.2, .55, distance1 + n2) * (1. - smoothstep(.45, .8, distance1 - n2));
    shape += smoothstep(.2, .55, distance2 + n2) * (1. - smoothstep(.45, .8, distance2 - n2));

    shape = pow(shape, 1.5);

  } else if (u_shape < 4.5) {
    // Corners

    shape_uv *= .6;
    vec2 outer = vec2(.5);

    vec2 bl = smoothstep(vec2(0.), outer, shape_uv + vec2(.1 + .1 * sin(3. * t), .2 - .1 * sin(5.25 * t)));
    vec2 tr = smoothstep(vec2(0.), outer, 1. - shape_uv);
    shape = 1. - bl.x * bl.y * tr.x * tr.y;

    shape_uv = -shape_uv;
    bl = smoothstep(vec2(0.), outer, shape_uv + vec2(.1 + .1 * sin(3. * t), .2 - .1 * cos(5.25 * t)));
    tr = smoothstep(vec2(0.), outer, 1. - shape_uv);
    shape -= bl.x * bl.y * tr.x * tr.y;

    shape = 1. - smoothstep(0., 1., shape);

  } else if (u_shape < 5.5) {
    // Ripple

    shape_uv *= 2.;
    float dist = length(.4 * shape_uv);
    float waves = sin(pow(dist, 1.2) * 5. - 3. * t) * .5 + .5;
    shape = waves;

  } else if (u_shape < 6.5) {
    // Blob

    t *= 2.;

    vec2 f1_traj = .25 * vec2(1.3 * sin(t), .2 + 1.3 * cos(.6 * t + 4.));
    vec2 f2_traj = .2 * vec2(1.2 * sin(-t), 1.3 * sin(1.6 * t));
    vec2 f3_traj = .25 * vec2(1.7 * cos(-.6 * t), cos(-1.6 * t));
    vec2 f4_traj = .3 * vec2(1.4 * cos(.8 * t), 1.2 * sin(-.6 * t - 3.));

    shape = .5 * pow(1. - clamp(0., 1., length(shape_uv + f1_traj)), 5.);
    shape += .5 * pow(1. - clamp(0., 1., length(shape_uv + f2_traj)), 5.);
    shape += .5 * pow(1. - clamp(0., 1., length(shape_uv + f3_traj)), 5.);
    shape += .5 * pow(1. - clamp(0., 1., length(shape_uv + f4_traj)), 5.);

    shape = smoothstep(.0, .9, shape);
    float edge = smoothstep(.25, .3, shape);
    shape = mix(.0, shape, edge);

  } else {
    // Sphere

    shape_uv *= 2.;
    float d = 1. - pow(length(shape_uv), 2.);
    vec3 pos = vec3(shape_uv, sqrt(max(d, 0.)));
    vec3 lightPos = normalize(vec3(cos(1.5 * t), .8, sin(1.25 * t)));
    shape = .5 + .5 * dot(lightPos, pos);
    shape *= step(0., d);
  }

  float baseNoise = snoise(grain_uv * .5);
  vec4 fbmVals = fbmR(
  .002 * grain_uv + 10.,
  .003 * grain_uv,
  .001 * grain_uv,
  rotate(.4 * grain_uv, 2.)
  );
  float grainDist = baseNoise * snoise(grain_uv * .2) - fbmVals.x - fbmVals.y;
  float rawNoise = .75 * baseNoise - fbmVals.w - fbmVals.z;
  float noise = clamp(rawNoise, 0., 1.);

  shape += u_intensity * 2. / u_colorsCount * (grainDist + .5);
  shape += u_noise * 10. / u_colorsCount * noise;

  float aa = fwidth(shape);

  shape = clamp(shape - .5 / u_colorsCount, 0., 1.);
  float totalShape = smoothstep(0., u_softness + 2. * aa, clamp(shape * u_colorsCount, 0., 1.));
  float mixer = shape * (u_colorsCount - 1.);

  int cntStop = int(u_colorsCount) - 1;
  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;
  for (int i = 1; i < ${po.maxColorCount}; i++) {
    if (i > cntStop) break;

    float localT = clamp(mixer - float(i - 1), 0., 1.);
    localT = smoothstep(.5 - .5 * u_softness - aa, .5 + .5 * u_softness + aa, localT);

    vec4 c = u_colors[i];
    c.rgb *= c.a;
    gradient = mix(gradient, c, localT);
  }

  vec3 color = gradient.rgb * totalShape;
  float opacity = gradient.a * totalShape;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1.0 - opacity);
  opacity = opacity + u_colorBack.a * (1.0 - opacity);

  fragColor = vec4(color, opacity);
}
`,Ko={wave:1,dots:2,truchet:3,corners:4,ripple:5,blob:6,sphere:7};var Je={maxColorCount:5,maxSpots:4},Jo=`#version 300 es
precision lowp float;

uniform float u_time;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${Je.maxColorCount}];
uniform float u_colorsCount;
uniform float u_roundness;
uniform float u_thickness;
uniform float u_marginLeft;
uniform float u_marginRight;
uniform float u_marginTop;
uniform float u_marginBottom;
uniform float u_aspectRatio;
uniform float u_softness;
uniform float u_intensity;
uniform float u_bloom;
uniform float u_spotSize;
uniform float u_spots;
uniform float u_pulse;
uniform float u_smoke;
uniform float u_smokeSize;

uniform sampler2D u_noiseTexture;

in vec2 v_responsiveUV;
in vec2 v_responsiveBoxGivenSize;
in vec2 v_patternUV;

out vec4 fragColor;

${P}

float beat(float time) {
  float first = pow(abs(sin(time * TWO_PI)), 10.);
  float second = pow(abs(sin((time - .15) * TWO_PI)), 10.);

  return clamp(first + 0.6 * second, 0.0, 1.0);
}

float sst(float edge0, float edge1, float x) {
  return smoothstep(edge0, edge1, x);
}

float roundedBox(vec2 uv, vec2 halfSize, float distance, float cornerDistance, float thickness, float softness) {
  float borderDistance = abs(distance);
  float aa = 2. * fwidth(distance);
  float border = 1. - sst(min(mix(thickness, -thickness, softness), thickness + aa), max(mix(thickness, -thickness, softness), thickness + aa), borderDistance);
  float cornerFadeCircles = 0.;
  cornerFadeCircles = mix(1., cornerFadeCircles, sst(0., 1., length((uv + halfSize) / thickness)));
  cornerFadeCircles = mix(1., cornerFadeCircles, sst(0., 1., length((uv - vec2(-halfSize.x, halfSize.y)) / thickness)));
  cornerFadeCircles = mix(1., cornerFadeCircles, sst(0., 1., length((uv - vec2(halfSize.x, -halfSize.y)) / thickness)));
  cornerFadeCircles = mix(1., cornerFadeCircles, sst(0., 1., length((uv - halfSize) / thickness)));
  aa = fwidth(cornerDistance);
  float cornerFade = sst(0., mix(aa, thickness, softness), cornerDistance);
  cornerFade *= cornerFadeCircles;
  border += cornerFade;
  return border;
}

${qe}

float randomG(vec2 p) {
  vec2 uv = floor(p) / 100. + .5;
  return texture(u_noiseTexture, fract(uv)).g;
}
float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = randomG(i);
  float b = randomG(i + vec2(1.0, 0.0));
  float c = randomG(i + vec2(0.0, 1.0));
  float d = randomG(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

void main() {
  const float firstFrameOffset = 109.;
  float t = 1.2 * (u_time + firstFrameOffset);

  vec2 borderUV = v_responsiveUV;
  float pulse = u_pulse * beat(.18 * u_time);

  float canvasRatio = v_responsiveBoxGivenSize.x / v_responsiveBoxGivenSize.y;
  vec2 halfSize = vec2(.5);
  borderUV.x *= max(canvasRatio, 1.);
  borderUV.y /= min(canvasRatio, 1.);
  halfSize.x *= max(canvasRatio, 1.);
  halfSize.y /= min(canvasRatio, 1.);

  float mL = u_marginLeft;
  float mR = u_marginRight;
  float mT = u_marginTop;
  float mB = u_marginBottom;
  float mX = mL + mR;
  float mY = mT + mB;

  if (u_aspectRatio > 0.) {
    float shapeRatio = canvasRatio * (1. - mX) / max(1. - mY, 1e-6);
    float freeX = shapeRatio > 1. ? (1. - mX) * (1. - 1. / max(abs(shapeRatio), 1e-6)) : 0.;
    float freeY = shapeRatio < 1. ? (1. - mY) * (1. - shapeRatio) : 0.;
    mL += freeX * 0.5;
    mR += freeX * 0.5;
    mT += freeY * 0.5;
    mB += freeY * 0.5;
    mX = mL + mR;
    mY = mT + mB;
  }

  float thickness = .5 * u_thickness * min(halfSize.x, halfSize.y);

  halfSize.x *= (1. - mX);
  halfSize.y *= (1. - mY);

  vec2 centerShift = vec2(
  (mL - mR) * max(canvasRatio, 1.) * 0.5,
  (mB - mT) / min(canvasRatio, 1.) * 0.5
  );

  borderUV -= centerShift;
  halfSize -= mix(thickness, 0., u_softness);

  float radius = mix(0., min(halfSize.x, halfSize.y), u_roundness);
  vec2 d = abs(borderUV) - halfSize + radius;
  float outsideDistance = length(max(d, .0001)) - radius;
  float insideDistance = min(max(d.x, d.y), .0001);
  float cornerDistance = abs(min(max(d.x, d.y) - .45 * radius, .0));
  float distance = outsideDistance + insideDistance;

  float borderThickness = mix(thickness, 3. * thickness, u_softness);
  float border = roundedBox(borderUV, halfSize, distance, cornerDistance, borderThickness, u_softness);
  border = pow(border, 1. + u_softness);

  vec2 smokeUV = .3 * u_smokeSize * v_patternUV;
  float smoke = clamp(3. * valueNoise(2.7 * smokeUV + .5 * t), 0., 1.);
  smoke -= valueNoise(3.4 * smokeUV - .5 * t);
  float smokeThickness = thickness + .2;
  smokeThickness = min(.4, max(smokeThickness, .1));
  smoke *= roundedBox(borderUV, halfSize, distance, cornerDistance, smokeThickness, 1.);
  smoke = 30. * smoke * smoke;
  smoke *= mix(0., .5, pow(u_smoke, 2.));
  smoke *= mix(1., pulse, u_pulse);
  smoke = clamp(smoke, 0., 1.);
  border += smoke;

  border = clamp(border, 0., 1.);

  vec3 blendColor = vec3(0.);
  float blendAlpha = 0.;
  vec3 addColor = vec3(0.);
  float addAlpha = 0.;

  float bloom = 4. * u_bloom;
  float intensity = 1. + (1. + 4. * u_softness) * u_intensity;

  float angle = atan(borderUV.y, borderUV.x) / TWO_PI;

  for (int colorIdx = 0; colorIdx < ${Je.maxColorCount}; colorIdx++) {
    if (colorIdx >= int(u_colorsCount)) break;
    float colorIdxF = float(colorIdx);

    vec3 c = u_colors[colorIdx].rgb * u_colors[colorIdx].a;
    float a = u_colors[colorIdx].a;

    for (int spotIdx = 0; spotIdx < ${Je.maxSpots}; spotIdx++) {
      if (spotIdx >= int(u_spots)) break;
      float spotIdxF = float(spotIdx);

      vec2 randVal = randomGB(vec2(spotIdxF * 10. + 2., 40. + colorIdxF));

      float time = (.1 + .15 * abs(sin(spotIdxF * (2. + colorIdxF)) * cos(spotIdxF * (2. + 2.5 * colorIdxF)))) * t + randVal.x * 3.;
      time *= mix(1., -1., step(.5, randVal.y));

      float mask = .5 + .5 * mix(
      sin(t + spotIdxF * (5. - 1.5 * colorIdxF)),
      cos(t + spotIdxF * (3. + 1.3 * colorIdxF)),
      step(mod(colorIdxF, 2.), .5)
      );

      float p = clamp(2. * u_pulse - randVal.x, 0., 1.);
      mask = mix(mask, pulse, p);

      float atg1 = fract(angle + time);
      float spotSize = .05 + .6 * pow(u_spotSize, 2.) + .05 * randVal.x;
      spotSize = mix(spotSize, .1, p);
      float sector = sst(.5 - spotSize, .5, atg1) * (1. - sst(.5, .5 + spotSize, atg1));

      sector *= mask;
      sector *= border;
      sector *= intensity;
      sector = clamp(sector, 0., 1.);

      vec3 srcColor = c * sector;
      float srcAlpha = a * sector;

      blendColor += ((1. - blendAlpha) * srcColor);
      blendAlpha = blendAlpha + (1. - blendAlpha) * srcAlpha;
      addColor += srcColor;
      addAlpha += srcAlpha;
    }
  }

  vec3 accumColor = mix(blendColor, addColor, bloom);
  float accumAlpha = mix(blendAlpha, addAlpha, bloom);
  accumAlpha = clamp(accumAlpha, 0., 1.);

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  vec3 color = accumColor + (1. - accumAlpha) * bgColor;
  float opacity = accumAlpha + (1. - accumAlpha) * u_colorBack.a;

  ${Z}

  fragColor = vec4(color, opacity);
}`,Zo={auto:0,square:1};var Ze={maxColorCount:7},$o=`#version 300 es
precision lowp float;

uniform float u_time;
uniform mediump float u_scale;

uniform vec4 u_colors[${Ze.maxColorCount}];
uniform float u_colorsCount;
uniform vec4 u_colorBack;
uniform float u_density;
uniform float u_angle1;
uniform float u_angle2;
uniform float u_length;
uniform bool u_edges;
uniform float u_blur;
uniform float u_fadeIn;
uniform float u_fadeOut;
uniform float u_gradient;

in vec2 v_objectUV;

out vec4 fragColor;

${P}

const float zLimit = .5;

vec2 getPanel(float angle, vec2 uv, float invLength, float aa) {
  float sinA = sin(angle);
  float cosA = cos(angle);

  float denom = sinA - uv.y * cosA;
  if (abs(denom) < .01) return vec2(0.);

  float z = uv.y / denom;

  if (z <= 0. || z > zLimit) return vec2(0.);

  float zRatio = z / zLimit;
  float panelMap = 1. - zRatio;
  float x = uv.x * (cosA * z + 1.) * invLength;

  float zOffset = zRatio - .5;
  float left = -.5 + zOffset * u_angle1;
  float right = .5 - zOffset * u_angle2;
  float blurX = aa + 2. * panelMap * u_blur;

  float leftEdge1 = left - blurX;
  float leftEdge2 = left + .25 * blurX;
  float rightEdge1 = right - .25 * blurX;
  float rightEdge2 = right + blurX;

  float panel = smoothstep(leftEdge1, leftEdge2, x) * (1.0 - smoothstep(rightEdge1, rightEdge2, x));
  panel *= mix(0., panel, smoothstep(0., .01 / u_scale, panelMap));

  float midScreen = abs(sinA);
  if (u_edges == true) {
    panelMap = mix(.99, panelMap, panel * clamp(panelMap / (.15 * (1. - pow(midScreen, .1))), 0.0, 1.0));
  } else if (midScreen < .07) {
    panel *= (midScreen * 15.);
  }

  return vec2(panel, panelMap);
}

vec4 blendColor(vec4 colorA, float panelMask, float panelMap) {
  float fade = 1. - smoothstep(.97 - .97 * u_fadeIn, 1., panelMap);

  fade *= smoothstep(-.2 * (1. - u_fadeOut), u_fadeOut, panelMap);

  vec3 blendedRGB = mix(vec3(0.), colorA.rgb, fade);
  float blendedAlpha = mix(0., colorA.a, fade);

  return vec4(blendedRGB, blendedAlpha) * panelMask;
}

void main() {
  vec2 uv = v_objectUV;
  uv *= 1.25;

  float t = .02 * u_time;
  t = fract(t);
  bool reverseTime = (t < 0.5);

  vec3 color = vec3(0.);
  float opacity = 0.;

  float aa = .005 / u_scale;
  int colorsCount = int(u_colorsCount);

  vec4 premultipliedColors[${Ze.maxColorCount}];
  for (int i = 0; i < ${Ze.maxColorCount}; i++) {
    if (i >= colorsCount) break;
    vec4 c = u_colors[i];
    c.rgb *= c.a;
    premultipliedColors[i] = c;
  }

  float invLength = 1.5 / max(u_length, .001);

  float totalColorWeight = 0.;
  int panelsNumber = 12;

  float densityNormalizer = 1.;
  if (colorsCount == 4) {
    panelsNumber = 16;
    densityNormalizer = 1.34;
  } else if (colorsCount == 5) {
    panelsNumber = 20;
    densityNormalizer = 1.67;
  } else if (colorsCount == 7) {
    panelsNumber = 14;
    densityNormalizer = 1.17;
  }

  float fPanelsNumber = float(panelsNumber);

  float totalPanelsShape = 0.;
  float panelGrad = 1. - clamp(u_gradient, 0., 1.);

  for (int set = 0; set < 2; set++) {
    bool isForward = (set == 0 && !reverseTime) || (set == 1 && reverseTime);
    if (!isForward) continue;

    for (int i = 0; i <= 20; i++) {
      if (i >= panelsNumber) break;

      int idx = panelsNumber - 1 - i;

      float offset = float(idx) / fPanelsNumber;
      if (set == 1) {
        offset += .5;
      }

      float densityFract = densityNormalizer * fract(t + offset);
      float angleNorm = densityFract / u_density;
      if (densityFract >= .5 || angleNorm >= .3) continue;

      float smoothDensity = clamp((.5 - densityFract) / .1, 0., 1.) * clamp(densityFract / .01, 0., 1.);
      float smoothAngle = clamp((.3 - angleNorm) / .05, 0., 1.);
      if (smoothDensity * smoothAngle < .001) continue;

      if (angleNorm > .5) {
        angleNorm = 0.5;
      }
      vec2 panel = getPanel(angleNorm * TWO_PI + PI, uv, invLength, aa);
      if (panel[0] <= .001) continue;
      float panelMask = panel[0] * smoothDensity * smoothAngle;
      float panelMap = panel[1];

      int colorIdx = idx % colorsCount;
      int nextColorIdx = (idx + 1) % colorsCount;

      vec4 colorA = premultipliedColors[colorIdx];
      vec4 colorB = premultipliedColors[nextColorIdx];

      colorA = mix(colorA, colorB, max(0., smoothstep(.0, .45, panelMap) - panelGrad));
      vec4 blended = blendColor(colorA, panelMask, panelMap);
      color = blended.rgb + color * (1. - blended.a);
      opacity = blended.a + opacity * (1. - blended.a);
    }


    for (int i = 0; i <= 20; i++) {
      if (i >= panelsNumber) break;

      int idx = panelsNumber - 1 - i;

      float offset = float(idx) / fPanelsNumber;
      if (set == 0) {
        offset += .5;
      }

      float densityFract = densityNormalizer * fract(-t + offset);
      float angleNorm = -densityFract / u_density;
      if (densityFract >= .5 || angleNorm < -.3) continue;

      float smoothDensity = clamp((.5 - densityFract) / .1, 0., 1.) * clamp(densityFract / .01, 0., 1.);
      float smoothAngle = clamp((angleNorm + .3) / .05, 0., 1.);
      if (smoothDensity * smoothAngle < .001) continue;

      vec2 panel = getPanel(angleNorm * TWO_PI + PI, uv, invLength, aa);
      float panelMask = panel[0] * smoothDensity * smoothAngle;
      if (panelMask <= .001) continue;
      float panelMap = panel[1];

      int colorIdx = (colorsCount - (idx % colorsCount)) % colorsCount;
      if (colorIdx < 0) colorIdx += colorsCount;
      int nextColorIdx = (colorIdx + 1) % colorsCount;

      vec4 colorA = premultipliedColors[colorIdx];
      vec4 colorB = premultipliedColors[nextColorIdx];

      colorA = mix(colorA, colorB, max(0., smoothstep(.0, .45, panelMap) - panelGrad));
      vec4 blended = blendColor(colorA, panelMask, panelMap);
      color = blended.rgb + color * (1. - blended.a);
      opacity = blended.a + opacity * (1. - blended.a);
    }
  }

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1.0 - opacity);
  opacity = opacity + u_colorBack.a * (1.0 - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`;var go={maxColorCount:10},et=`#version 300 es
precision mediump float;

uniform vec4 u_colors[${go.maxColorCount}];
uniform float u_colorsCount;

uniform float u_positions;
uniform float u_waveX;
uniform float u_waveXShift;
uniform float u_waveY;
uniform float u_waveYShift;
uniform float u_mixing;
uniform float u_grainMixer;
uniform float u_grainOverlay;

in vec2 v_objectUV;
out vec4 fragColor;

${P}
${L}
${me}

float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

float noise(vec2 n, vec2 seedOffset) {
  return valueNoise(n + seedOffset);
}

vec2 getPosition(int i, float t) {
  float a = float(i) * .37;
  float b = .6 + mod(float(i), 3.) * .3;
  float c = .8 + mod(float(i + 1), 4.) * 0.25;

  float x = sin(t * b + a);
  float y = cos(t * c + a * 1.5);

  return .5 + .5 * vec2(x, y);
}

void main() {
  vec2 uv = v_objectUV;
  uv += .5;
  vec2 grainUV = uv * 1000.;

  float mixerGrain = 0.;
  if (u_grainMixer > 0.) {
    mixerGrain = .4 * u_grainMixer * (noise(grainUV, vec2(0.)) - .5);
  }

  float radius = smoothstep(0., 1., length(uv - .5));
  float center = 1. - radius;
  for (float i = 1.; i <= 2.; i++) {
    uv.x += u_waveX * center / i * cos(TWO_PI * u_waveXShift + i * 2. * smoothstep(.0, 1., uv.y));
    uv.y += u_waveY * center / i * cos(TWO_PI * u_waveYShift + i * 2. * smoothstep(.0, 1., uv.x));
  }

  vec3 color = vec3(0.);
  float opacity = 0.;
  float totalWeight = 0.;
  float positionSeed = 25. + .33 * u_positions;

  for (int i = 0; i < ${go.maxColorCount}; i++) {
    if (i >= int(u_colorsCount)) break;

    vec2 pos = getPosition(i, positionSeed) + mixerGrain;
    float dist = length(uv - pos);

    vec3 colorFraction = u_colors[i].rgb * u_colors[i].a;
    float opacityFraction = u_colors[i].a;

    float mixing = pow(u_mixing, .7);
    float power = mix(2., 1., mixing);
    dist = pow(dist, power);

    float w = 1. / (dist + 1e-3);
    float baseSharpness = mix(.0, 8., clamp(w, 0., 1.));
    float sharpness = mix(baseSharpness, 1., mixing);
    w = pow(w, sharpness);
    color += colorFraction * w;
    opacity += opacityFraction * w;
    totalWeight += w;
  }

  color /= max(1e-4, totalWeight);
  opacity /= max(1e-4, totalWeight);

  if (u_grainOverlay > 0.) {
    float grainOverlay = valueNoise(rotate(grainUV, 1.) + vec2(3.));
    grainOverlay = mix(grainOverlay, valueNoise(rotate(grainUV, 2.) + vec2(-1.)), .5);
    grainOverlay = pow(grainOverlay, 1.3);

    float grainOverlayV = grainOverlay * 2. - 1.;
    vec3 grainOverlayColor = vec3(step(0., grainOverlayV));
    float grainOverlayStrength = u_grainOverlay * abs(grainOverlayV);
    grainOverlayStrength = pow(grainOverlayStrength, .8);
    color = mix(color, grainOverlayColor, .35 * grainOverlayStrength);

    opacity += .5 * grainOverlayStrength;
  }
  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`;var ho={maxColorCount:10},ot=`#version 300 es
precision mediump float;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${ho.maxColorCount}];
uniform float u_colorsCount;

uniform float u_radius;
uniform float u_focalDistance;
uniform float u_focalAngle;
uniform float u_falloff;
uniform float u_mixing;
uniform float u_distortion;
uniform float u_distortionShift;
uniform float u_distortionFreq;
uniform float u_grainMixer;
uniform float u_grainOverlay;

in vec2 v_objectUV;
out vec4 fragColor;

${P}
${L}
${me}

float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

float noise(vec2 n, vec2 seedOffset) {
  return valueNoise(n + seedOffset);
}

vec2 getPosition(int i, float t) {
  float a = float(i) * .37;
  float b = .6 + mod(float(i), 3.) * .3;
  float c = .8 + mod(float(i + 1), 4.) * 0.25;

  float x = sin(t * b + a);
  float y = cos(t * c + a * 1.5);

  return .5 + .5 * vec2(x, y);
}

void main() {
  vec2 uv = 2. * v_objectUV;
  vec2 grainUV = uv * 1000.;

  vec2 center = vec2(0.);
  float angleRad = -radians(u_focalAngle + 90.);
  vec2 focalPoint = vec2(cos(angleRad), sin(angleRad)) * u_focalDistance;
  float radius = u_radius;

  vec2 c_to_uv = uv - center;
  vec2 f_to_uv = uv - focalPoint;
  vec2 f_to_c = center - focalPoint;
  float r = length(c_to_uv);

  float fragAngle = atan(c_to_uv.y, c_to_uv.x);
  float angleDiff = fract((fragAngle - angleRad + PI) / TWO_PI) * TWO_PI - PI;

  float halfAngle = acos(clamp(radius / max(u_focalDistance, 1e-4), 0.0, 1.0));
  float e0 = 0.6 * PI, e1 = halfAngle;
  float lo = min(e0, e1), hi = max(e0, e1);
  float s  = smoothstep(lo, hi, abs(angleDiff));
  float isInSector = (e1 >= e0) ? (1.0 - s) : s;

  float a = dot(f_to_uv, f_to_uv);
  float b = -2.0 * dot(f_to_uv, f_to_c);
  float c = dot(f_to_c, f_to_c) - radius * radius;

  float discriminant = b * b - 4.0 * a * c;
  float t = 1.0;

  if (discriminant >= 0.0) {
    float sqrtD = sqrt(discriminant);
    float div = max(1e-4, 2.0 * a);
    float t0 = (-b - sqrtD) / div;
    float t1 = (-b + sqrtD) / div;
    t = max(t0, t1);
    if (t < 0.0) t = 0.0;
  }

  float dist = length(f_to_uv);
  float normalized = dist / max(1e-4, length(f_to_uv * t));
  float shape = clamp(normalized, 0.0, 1.0);

  float falloffMapped = mix(.2 + .8 * max(0., u_falloff + 1.), mix(1., 15., u_falloff * u_falloff), step(.0, u_falloff));

  float falloffExp = mix(falloffMapped, 1., shape);
  shape = pow(shape, falloffExp);
  shape = 1. - clamp(shape, 0., 1.);


  float outerMask = .002;
  float outer = 1.0 - smoothstep(radius - outerMask, radius + outerMask, r);
  outer = mix(outer, 1., isInSector);

  shape = mix(0., shape, outer);
  shape *= 1. - smoothstep(radius - .01, radius, r);

  float angle = atan(f_to_uv.y, f_to_uv.x);
  shape -= pow(u_distortion, 2.) * shape * pow(abs(sin(PI * clamp(length(f_to_uv) - 0.2 + u_distortionShift, 0.0, 1.0))), 4.0) * (sin(u_distortionFreq * angle) + cos(floor(0.65 * u_distortionFreq) * angle));

  float mixerGrain = 0.;
  if (u_grainMixer > 0.) {
    mixerGrain = .4 * u_grainMixer * (noise(grainUV, vec2(0.)) - .5);
  }

  float mixer = shape * u_colorsCount + mixerGrain;
  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;

  float outerShape = 0.;
  for (int i = 1; i < ${ho.maxColorCount+1}; i++) {
    if (i > int(u_colorsCount)) break;
    float mLinear = clamp(mixer - float(i - 1), 0.0, 1.0);

    float aa = fwidth(mLinear);
    float width = min(u_mixing, 0.5);
    float t = clamp((mLinear - (0.5 - width - aa)) / (2. * width + 2. * aa), 0., 1.);
    float p = mix(2., 1., clamp((u_mixing - 0.5) * 2., 0., 1.));
    float m = t < 0.5
      ? 0.5 * pow(2. * t, p)
      : 1. - 0.5 * pow(2. * (1. - t), p);

    float quadBlend = clamp((u_mixing - 0.5) * 2., 0., 1.);
    m = mix(m, m * m, 0.5 * quadBlend);
    
    if (i == 1) {
      outerShape = m;
    }

    vec4 c = u_colors[i - 1];
    c.rgb *= c.a;
    gradient = mix(gradient, c, m);
  }

  vec3 color = gradient.rgb * outerShape;
  float opacity = gradient.a * outerShape;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1.0 - opacity);
  opacity = opacity + u_colorBack.a * (1.0 - opacity);

  if (u_grainOverlay > 0.) {
    float grainOverlay = valueNoise(rotate(grainUV, 1.) + vec2(3.));
    grainOverlay = mix(grainOverlay, valueNoise(rotate(grainUV, 2.) + vec2(-1.)), .5);
    grainOverlay = pow(grainOverlay, 1.3);

    float grainOverlayV = grainOverlay * 2. - 1.;
    vec3 grainOverlayColor = vec3(step(0., grainOverlayV));
    float grainOverlayStrength = u_grainOverlay * abs(grainOverlayV);
    grainOverlayStrength = pow(grainOverlayStrength, .8);
    color = mix(color, grainOverlayColor, .35 * grainOverlayStrength);

    opacity += .5 * grainOverlayStrength;
  }
  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`;var $e={maxCrumpleCount:15},tt=`#version 300 es
precision mediump float;

uniform sampler2D u_image;
uniform bool u_isImage;
uniform float u_imageAspectRatio;

uniform vec4 u_colorBack;
uniform vec4 u_colorPaper;
uniform vec4 u_colorShadow;

uniform float u_blending;
uniform float u_distortion;
uniform bool u_clip;
uniform float u_angle;
uniform float u_seed;

uniform float u_roughness;
uniform float u_roughnessSize;
uniform float u_roughnessRows;
uniform float u_fiber;
uniform float u_fiberSize;
uniform float u_folds;
uniform float u_foldSizeX;
uniform float u_foldSizeY;
uniform float u_foldOffsetX;
uniform float u_foldOffsetY;
uniform float u_wrinkles;
uniform float u_wrinkleSize;
uniform float u_crumples;
uniform float u_crumpleCount;
uniform float u_drops;

uniform sampler2D u_noiseTexture;

in vec2 v_imageUV;
out vec4 fragColor;

float getUvFrame(vec2 uv) {
  vec2 invAA = .5 / clamp(fwidth(uv), 1e-5, .02);
  vec2 lo = clamp(uv * invAA + .5, 0., 1.);
  vec2 hi = clamp((1. - uv) * invAA + .5, 0., 1.);
  return lo.x * hi.x * lo.y * hi.y;
}

float lst(float edge0, float edge1, float x) {
  return clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
}

${P}
${me}
${Ft}

float getRoughness(vec2 p, vec2 lightDir, vec2 seedShift, float basePixel) {
  vec2 u = p / vec2(2, 4);
  float w = 100. * basePixel;
  float eps = 4. * w;

  float size = mix(3.2, .8, u_roughnessSize);
  float logLac = log2(2.1);
  float level = -log2(w + 1e-8) / logLac;
  float baseLevel = floor(level) - 2.;
  float fade = fract(level);

  vec2 px = (u.x + vec2(eps, -eps)) * .1;
  float py = u.y * .1;

  vec2 sum = vec2(0.);
  float norm = 0., amp = .5;
  float freq = exp2(baseLevel * logLac);
  for (int i = 0; i < 4; i++) {
    float absIdx = baseLevel + float(i);
    vec2 qx = size * px * freq;
    float qy = size * py * freq;

    float wi = 1.;
    if (i == 0) wi = 1. - fade;
    if (i == 3) wi = fade;

    vec2 fx = fract(qx);
    float fy = fract(qy);
    vec2 shift = .5 + absIdx * .3 + seedShift;
    float uvY = floor(qy) / 50. + shift.y;
    vec2 s0a = textureLod(u_noiseTexture, fract(vec2(floor(qx.x) / 50. + shift.x, uvY)), 0.).rg;
    vec2 s1a = textureLod(u_noiseTexture, fract(vec2( ceil(qx.x) / 50. + shift.x, uvY)), 0.).rg;
    vec2 s0b = textureLod(u_noiseTexture, fract(vec2(floor(qx.y) / 50. + shift.x, uvY)), 0.).rg;
    vec2 s1b = textureLod(u_noiseTexture, fract(vec2( ceil(qx.y) / 50. + shift.x, uvY)), 0.).rg;
    vec2 ny0 = mix(vec2(s0a.r, s0b.r), vec2(s0a.g, s0b.g), fy);
    vec2 ny1 = mix(vec2(s1a.r, s1b.r), vec2(s1a.g, s1b.g), fy);
    vec2 n = mix(ny0, ny1, fx);

    sum += amp * wi * n;
    norm += amp * wi;
    amp *= .8;
    freq *= 2.1;
  }

  vec2 r = sum / norm;
  float dx = .5 + r.x - r.y;
  float grain = 3. * dx * dx - .7;

  float rowBand = fract(dot(p, lightDir) * .05 * size);
  return grain + .6 * u_roughnessRows * (rowBand - .5);
}

float getFiber(vec2 p, vec2 seedShift, float basePixel) {
  float size = mix(4., 1., u_fiberSize);
  float w = 50. * basePixel;
  float level = -log2(w + 1e-8);
  float baseLevel = floor(level) - 3.;
  float fade = fract(level);

  vec2 grad = vec2(0.);
  float scale = 1.;
  float amp = 1.;
  float freq = pow(1.7, baseLevel);
  for (int i = 0; i < 5; i++) {
    float absIdx = baseLevel + float(i);
    vec2 q = size * p * freq;

    float an = absIdx * .8;
    float rc = cos(an), rs = sin(an);
    q = vec2(rc * q.x - rs * q.y, rs * q.x + rc * q.y);

    float wi = 1.;
    if (i == 0) wi = 1. - fade;
    if (i == 4) wi = fade;

    vec2 iq = floor(q);
    vec2 fq = fract(q);
    float shift = absIdx * .3;
    vec4 uv = fract(vec4(iq, iq + 1.) / 50. + .5 + shift + seedShift.xyxy);
    float aF = textureLod(u_noiseTexture, uv.xy, 0.).b;
    float bF = textureLod(u_noiseTexture, uv.zy, 0.).b;
    float cF = textureLod(u_noiseTexture, uv.xw, 0.).b;
    float dF = textureLod(u_noiseTexture, uv.zw, 0.).b;
    vec2 u = fq * fq * (3. - 2. * fq);
    vec2 du = 8. * fq * (1. - fq);
    float dx = du.x * mix(bF - aF, dF - cF, u.y);
    float dy = du.y * mix(cF - aF, dF - bF, u.x);
    grad += wi * amp * scale * vec2(rc * dx + rs * dy, -rs * dx + rc * dy);
    scale *= 1.7;
    amp *= .5;
    freq *= 1.7;
  }

  return clamp(.333 * length(grad), 0., 1.);
}

vec2 smoothNoise(vec2 p) {
  vec2 t = p * 50. - .5;
  vec2 i = floor(t);
  vec2 f = fract(t);
  f = f * f * (3. - 2. * f);
  return textureLod(u_noiseTexture, fract((i + f + .5) / vec2(50.)), 0.).rg;
}

float getDrops(vec2 uv, vec2 seedShift) {
  vec2 iDropsUV = floor(uv);
  vec2 fDropsUV = fract(uv);
  float dropsMinDist = 1.;
  for (int y = -1; y < 2; y += 1) {
    for (int x = -1; x < 2; x += 1) {
      vec2 neighbor = vec2(float(y), float(x));
      vec2 offset = hash22(iDropsUV + neighbor + 50. * seedShift);
      vec2 pos = neighbor + offset - fDropsUV;
      dropsMinDist *= min(1., dot(pos, pos));
    }
  }
  return .5 * lst(.09, .08, sqrt(sqrt(dropsMinDist)));
}

vec2 getCellTilt(float idx, float radius) {
  vec2 rand = hash22(vec2(idx + 31., idx * u_seed + 17.));
  float an = rand.x * TWO_PI;
  return vec2(cos(an), sin(an)) * mix(.3, 1.7, rand.y * rand.y) * mix(.7, 1., radius);
}

vec2 getCrumpleDetail(vec2 uv, float freq, float shift, float basePixel, out float depth) {
  depth = 0.;
  vec2 v = uv * freq;
  float pixel = .9 * freq * basePixel;
  vec2 base = floor(v);
  float n1 = 9., n2 = 9.;
  vec2 s1 = vec2(0.), s2 = vec2(0.), q1 = vec2(0.), q2 = vec2(0.);

  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 cell = base + vec2(float(x), float(y));
      vec2 q = hash22(vec2(cell.y * 1.9 + 3.1 + shift, cell.x * 1.3 + .11 * u_seed));
      float keep = .8;
      if (q.y > keep) continue;

      vec2 r = hash22(vec2(cell.x + .37 * u_seed + shift + 11.1, cell.y - .21 * u_seed + 5.7));
      vec2 s = cell + .06 + .88 * r;

      vec2 d = v - s;
      float dsq = dot(d, d);
      if (dsq < n1) {
        n2 = n1;
        s2 = s1;
        q2 = q1;
        n1 = dsq;
        s1 = s;
        q1 = q;
      } else if (dsq < n2) {
        n2 = dsq;
        s2 = s;
        q2 = q;
      }
    }
  }

  if (n1 > 8.) return vec2(0.);

  float an1 = q1.x * TWO_PI, mag1 = q1.y / .8;
  vec2 t1 = vec2(cos(an1), sin(an1)) * mix(.3, 1.7, mag1 * mag1);
  float an2 = q2.x * TWO_PI, mag2 = q2.y / .8;
  vec2 t2 = vec2(cos(an2), sin(an2)) * mix(.3, 1.7, mag2 * mag2);

  vec2 span = s1 - s2;
  float spanLen = max(length(span), 1e-4);
  float toEdge = (n2 - n1) / (2. * spanLen);

  float pair = hash21(s1 + s2 + 1.7 * abs(s1 - s2));
  float pairSoft = .05 + .1 * step(pair, .4);
  float b = clamp(toEdge / max(1.5 * pixel, .5 * pairSoft), 0., 1.);
  b = b * b * (3. - 2. * b);
  float d1 = max(sqrt(n1), 1e-4);
  depth = .2 * d1;
  float shoulderAmt = max(0., 1. - toEdge / .42) * b;
  vec2 shoulder = vec2(0.);
  if (shoulderAmt > 0.) {
    float d2 = max(sqrt(n2), 1e-4);
    shoulder = shoulderAmt * ((v - s2) / d2 - (v - s1) / d1);
  }

  vec2 mid = .5 * (t1 + t2);
  return mid + (t1 - mid) * b + .9 * shoulder;
}

vec4 getCrumples(vec2 uv) {
  float crumpleN = max(2., floor(u_crumpleCount + .5));
  float near = 60000., nearB = 60000.;
  float idx = 0., rad = 0.;
  vec2 nearP = vec2(0.), nearPb = vec2(0.);
  vec4 seeds[${$e.maxCrumpleCount}];
  for (int i = 0; i < ${$e.maxCrumpleCount}; i++) {
    if (float(i) >= crumpleN) break;
    vec2 rand = hash22(vec2(float(i), float(i) * u_seed));
    float an = rand.x * TWO_PI;
    vec2 p = vec2(cos(an), sin(an)) * rand.y;
    seeds[i] = vec4(p, rand);

    vec2 d = uv - p;
    float dsq = dot(d, d);
    if (dsq < near) {
      nearB = near;
      nearPb = nearP;
      near = dsq;
      idx = float(i);
      rad = rand.y;
      nearP = p;
    } else if (dsq < nearB) {
      nearB = dsq;
      nearPb = p;
    }
  }
  float l = sqrt(near), lb = sqrt(nearB);
  vec2 dir = (uv - nearP) / max(l, 1e-4);
  float edge = lst(0., .5, lb - l);

  float shoulderLimit = l + .5;

  vec2 tilt = getCellTilt(idx, rad);
  float tiltSum = 1.;
  vec2 wide = vec2(0.);
  float wideSum = 0.;
  float toEdge = 9., edgeSoft = 0.;

  for (int i = 0; i < ${$e.maxCrumpleCount}; i++) {
    if (float(i) >= crumpleN) break;
    if (float(i) == idx) continue;
    vec4 seed = seeds[i];
    vec2 p = seed.xy;
    vec2 rand = seed.zw;

    vec2 d = uv - p;
    float dsq = dot(d, d);

    if (dsq < shoulderLimit * shoulderLimit) {
      float di = sqrt(dsq);
      float shoulder = lst(.5, 0., di - l);
      wide += shoulder * (d / max(di, 1e-4) - dir);
      wideSum += shoulder;
    }

    float pairSoft = .01 + .05 * step(.2, rand.x) + .3 * rand.y;
    float toBisector = (dsq - near) / (.2 * max(length(p - nearP), 1e-4));
    if (toBisector < toEdge) {
      toEdge = toBisector;
      edgeSoft = pairSoft;
    }

    float w = 1. - toBisector / pairSoft;
    if (w > 0.) {
      w *= w;
      tilt += w * getCellTilt(float(i), rand.y);
      tiltSum += w;
    }
  }

  float blend = clamp(toEdge / edgeSoft, 0., 1.);
  vec2 sharp = (1. - edge) * ((uv - nearPb) / max(lb, 1e-4) - dir);
  vec2 rounding = mix(sharp, wide / max(wideSum, 1.), min(2. * edgeSoft, 1.));
  float radial = l / max(l + toEdge, 1e-4);

  return vec4(tilt / tiltSum + rounding * blend * radial, .2 * l, edge);
}

void getFolds(vec2 coord, vec2 offset, vec2 count, vec2 noise, vec2 baseFwidth, out vec2 slope, out vec2 dark, out vec2 lift) {
  vec2 g = coord * count + .5 * offset + noise;
  vec2 dx = fract(g) - .5;
  vec2 adx = abs(dx);
  float foldRadius = .3;
  vec2 t = clamp(adx / foldRadius, 0., 1.);
  dark = t * t * (3. - 2. * t);
  lift = 1. - t;
  lift *= lift;

  vec2 crease = clamp(dx / max(count * baseFwidth, 1e-5), -1., 1.);
  slope = crease * (1. - dark);

  vec2 lineWidth = .02 * count * mix(vec2(2.5), vec2(.8), dark.yx) + .1 * noise;
  slope -= 1. - smoothstep(vec2(0.), lineWidth, adx);
}

void main() {

  vec2 patternUV = (v_imageUV - .5) * vec2(u_imageAspectRatio, 1.);
  float basePixel = max(length(dFdx(patternUV)), length(dFdy(patternUV)));
  vec2 baseFwidth = fwidth(patternUV);

  float pattern = 0.;

  float crumpleDepth = 0.;
  float wrinkleDepth = 0.;
  float foldDepth = 0.;
  float roughness = 0.;
  float fiber = 0.;
  float drops = 0.;

  float grazing = 0.7;
  float lightRad = radians(u_angle);
  vec2 lightDir = vec2(sin(lightRad), -cos(lightRad));
  float foldAngleInSector = mod(u_angle, 90.);
  float foldLightRad = radians(u_angle - foldAngleInSector + mix(12., 78., foldAngleInSector / 90.));
  vec2 foldLightDir = vec2(sin(foldLightRad), -cos(foldLightRad));
  vec2 relief = vec2(0.);
  vec2 foldSlope = vec2(0.);
  float reliefAmount = 0.;
  float foldInk = 1.;
  vec2 crumpleFlow = vec2(0.);

  vec2 warpNoise = vec2(0.);
  if (u_crumples > 0. || u_folds > 0. || u_wrinkles > 0.) {
    warpNoise = smoothNoise(patternUV * .1 + .2 + .6 * fract(.017 * u_seed)) - .5;
  }
  vec2 crumplesUV = (patternUV * .9) + .012 * warpNoise;

  if (u_crumples > 0.) {
    vec4 crumples = getCrumples(crumplesUV);

    vec2 crumpleTilt = .5 * u_crumples * crumples.xy;
    crumpleTilt -= .1 * max(dot(crumpleTilt, lightDir), 0.) * lightDir;
    relief += crumpleTilt;
    reliefAmount += .6 * u_crumples;
    crumpleFlow = crumples.w * crumpleTilt;

    crumpleDepth = clamp(5. * crumples.z, 0., 1.);
  }

  if (u_wrinkles > 0.) {
    float detailFreq = mix(10., 1., u_wrinkleSize);
    float detailAmp = .2;
    vec2 detailGrad = vec2(0.);
    float detailDepth = 0., depthSum = 0.;
    for (int i = 0; i < 3; i++) {
      float layerDepth;
      detailGrad += detailAmp * getCrumpleDetail(crumplesUV, detailFreq, 31. * float(i), basePixel, layerDepth);
      detailDepth += detailAmp * layerDepth;
      depthSum += detailAmp;
      detailAmp *= (.5 + .2 * detailGrad.x);
      detailFreq *= 2.1;
    }

    vec2 detailTilt = 1.5 * u_wrinkles * detailGrad;
    detailTilt -= .65 * max(dot(detailTilt, lightDir), 0.) * lightDir;
    relief += detailTilt;
    reliefAmount += .6 * u_wrinkles;

    wrinkleDepth = clamp(5. * detailDepth / max(depthSum, 1e-4), 0., 1.);
  }

  if (u_folds > 0.) {
    vec2 foldOffset = vec2(1. - 2. * u_foldOffsetX, 1. - 2. * u_foldOffsetY);
    vec2 foldCount = vec2(mix(3., .5, u_foldSizeX), mix(3., .5, u_foldSizeY));
    vec2 foldNoise = .005 * warpNoise * foldCount;
    vec2 uv = patternUV + .03 * crumpleFlow;

    vec2 slope, dark, lift;
    getFolds(uv, foldOffset, foldCount, foldNoise, baseFwidth, slope, dark, lift);

    foldSlope = u_folds * slope;
    reliefAmount += 1. * u_folds;
    vec2 ink = mix(vec2(.96), vec2(1.), dark);
    float flatness = dark.x * dark.y;
    foldInk *= mix(1., ink.x * ink.y * mix(.5, .3, flatness), u_folds);

    foldDepth = u_folds * (lift.y * foldLightDir.y - lift.x * foldLightDir.x);
  }

  float unlit = cos(grazing);
  float lit = unlit;

  if (reliefAmount > 0.) {
    float lightFalloff = clamp(.5 + dot(v_imageUV - .5, lightDir), 0., 1.);
    float lightPower = mix(.5, 1., lightFalloff);
    float slope = clamp(dot(relief, lightDir) + dot(foldSlope, foldLightDir), -1.2, 1.2);
    lit = max(cos(slope + grazing), 0.);

    pattern += (clamp(reliefAmount, 0., 1.) * unlit + (lit - unlit)) * foldInk * lightPower;
  }

  patternUV += .04 * crumpleFlow;

  vec2 seedShift = floor(fract(u_seed * vec2(.7548776662, .5698402909)) * 50.) / 50.;

  if (u_roughness > 0.) {
    roughness = u_roughness * getRoughness(1000. * patternUV, lightDir, seedShift, basePixel);
    pattern += roughness;
  }

  if (u_fiber > 0.) {
    fiber = u_fiber * getFiber(50. * patternUV, seedShift, basePixel);
    pattern += fiber;
  }

  if (u_drops > 0.) {
    drops = u_drops * getDrops(patternUV * 10., seedShift);
  }

  pattern = clamp(pattern, 0., 1.);

  vec3 backColor = u_colorBack.rgb * u_colorBack.a;
  float backOpacity = u_colorBack.a;
  vec3 baseColor = u_colorPaper.rgb * u_colorPaper.a;
  float baseOpacity = u_colorPaper.a;
  vec3 shadowColor = u_colorShadow.rgb * u_colorShadow.a;
  float shadowOpacity = u_colorShadow.a;

  float notClipped = u_clip ? .1 : 1.;
  vec2 imageCenteredUV = v_imageUV - .5;
  float edgeDist = 2. * max(abs(imageCenteredUV.x), abs(imageCenteredUV.y));
  float wrinkleDistortion = mix(.38, .0175, smoothstep(0., 1., edgeDist));
  float scaleDistortion = .15 * u_crumples * (crumpleDepth - .5) + wrinkleDistortion * u_wrinkles * (wrinkleDepth - .5) + .05 * foldDepth;
  vec2 linearDistortion = notClipped * .002 * lightDir * drops;
  float radialDistortion = notClipped * .02 * (roughness + fiber);
  vec2 centeredUV = imageCenteredUV * (1. - u_distortion * scaleDistortion);
  centeredUV -= u_distortion * linearDistortion;
  vec2 imageUV = .5 + centeredUV * (1. - abs(u_distortion) * radialDistortion * dot(centeredUV, centeredUV));

  vec3 color = shadowColor * pattern;
  float opacity = shadowOpacity * pattern;
  color += baseColor * (1. - opacity);
  opacity += baseOpacity * (1. - opacity);

  if (u_isImage) {
    float frame = getUvFrame(imageUV);
    vec4 image = texture(u_image, imageUV);
    frame *= image.a;

    float maxC = max(max(image.r, image.g), image.b);
    float minC = min(min(image.r, image.g), image.b);
    float sat = maxC > 0. ? (maxC - minC) / maxC : 0.;
    float midC = image.r + image.g + image.b - maxC - minC;
    float secondaryness = maxC > minC ? (midC - minC) / (maxC - minC) : 0.;
    float satDampen = sat * (1. - .5 * secondaryness);
    float darkDampen = 1. - dot(vec3(.2126, .7152, .0722), image.rgb);
    float dampen = mix(0., .7, u_blending) * max(satDampen, darkDampen);

    vec3 paper = vec3(1.) - opacity + color;
    vec3 pic = image.rgb * paper * u_blending + image.rgb * (1. - u_blending);
    pic = mix(pic, vec3(1.), .6 * pow(dampen, 2. + 3. * pattern));

    color = mix(color, pic, frame);
    opacity = frame + opacity * (1. - frame);

    if (u_clip) {
      color *= frame;
      opacity *= frame;
    }
  }

  color *= mix(vec3(1.), .5 * u_colorShadow.rgb, drops * shadowOpacity);

  color += backColor * (1. - opacity);
  opacity += backOpacity * (1. - opacity);

  fragColor = vec4(color, opacity);
}
`;var at=`#version 300 es
precision mediump float;

uniform float u_time;

uniform vec4 u_colorBack;
uniform vec4 u_colorHighlight;

uniform sampler2D u_image;
uniform float u_imageAspectRatio;

uniform float u_size;
uniform float u_highlights;
uniform float u_layering;
uniform float u_edges;
uniform float u_caustic;
uniform float u_waves;

in vec2 v_imageUV;

out vec4 fragColor;

${P}
${L}
${Me}

float getUvFrame(vec2 uv) {
  float aax = 2. * fwidth(uv.x);
  float aay = 2. * fwidth(uv.y);

  float left   = smoothstep(0., aax, uv.x);
  float right = 1.0 - smoothstep(1. - aax, 1., uv.x);
  float bottom = smoothstep(0., aay, uv.y);
  float top = 1.0 - smoothstep(1. - aay, 1., uv.y);

  return left * right * bottom * top;
}

mat2 rotate2D(float r) {
  return mat2(cos(r), sin(r), -sin(r), cos(r));
}

float getCausticNoise(vec2 uv, float t, float scale) {
  vec2 n = vec2(.1);
  vec2 N = vec2(.1);
  mat2 m = rotate2D(.5);
  for (int j = 0; j < 6; j++) {
    uv *= m;
    n *= m;
    vec2 q = uv * scale + float(j) + n + (.5 + .5 * float(j)) * (mod(float(j), 2.) - 1.) * t;
    n += sin(q);
    N += cos(q) / scale;
    scale *= 1.1;
  }
  return (N.x + N.y + 1.);
}

void main() {
  vec2 imageUV = v_imageUV;
  vec2 patternUV = v_imageUV - .5;
  patternUV = (patternUV * vec2(u_imageAspectRatio, 1.));
  patternUV /= (.01 + .09 * u_size);

  float t = u_time;

  float wavesNoise = snoise((.3 + .1 * sin(t)) * .1 * patternUV + vec2(0., .4 * t));

  float causticNoise = getCausticNoise(patternUV + u_waves * vec2(1., -1.) * wavesNoise, 2. * t, 1.5);

  if (u_layering > 0.) {
    causticNoise += u_layering * getCausticNoise(patternUV + 2. * u_waves * vec2(1., -1.) * wavesNoise, 1.5 * t, 2.);
  }
  causticNoise = causticNoise * causticNoise;

  float edgesDistortion = smoothstep(0., .1, imageUV.x);
  edgesDistortion *= smoothstep(0., .1, imageUV.y);
  edgesDistortion *= (smoothstep(1., 1.1, imageUV.x) + (1.0 - smoothstep(.8, .95, imageUV.x)));
  edgesDistortion *= (1.0 - smoothstep(.9, 1., imageUV.y));
  edgesDistortion = mix(edgesDistortion, 1., u_edges);

  float causticNoiseDistortion = .02 * causticNoise * edgesDistortion;

  float wavesDistortion = .1 * u_waves * wavesNoise;

  imageUV += vec2(wavesDistortion, -wavesDistortion);
  imageUV += (u_caustic * causticNoiseDistortion);

  float frame = getUvFrame(imageUV);

  vec4 image = texture(u_image, imageUV);
  vec4 backColor = u_colorBack;
  backColor.rgb *= backColor.a;

  vec3 color = mix(backColor.rgb, image.rgb, image.a * frame);
  float opacity = backColor.a + image.a * frame;

  causticNoise = max(-.2, causticNoise);

  float hightlight = .025 * u_highlights * causticNoise;
  hightlight *= u_colorHighlight.a;
  color = mix(color, u_colorHighlight.rgb, .05 * u_highlights * causticNoise * u_colorHighlight.a);
  opacity += hightlight;

  color += hightlight * (.5 + .5 * wavesNoise);
  opacity += hightlight * (.5 + .5 * wavesNoise);

  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`;var rt=`#version 300 es
precision mediump float;

uniform vec2 u_resolution;
uniform float u_pixelRatio;

uniform vec4 u_colorBack;
uniform vec4 u_colorShadow;
uniform vec4 u_colorHighlight;

uniform sampler2D u_image;
uniform float u_imageAspectRatio;

uniform float u_size;
uniform float u_shadows;
uniform float u_angle;
uniform float u_stretch;
uniform float u_shape;
uniform float u_distortion;
uniform float u_highlights;
uniform float u_distortionShape;
uniform float u_shift;
uniform float u_blur;
uniform float u_edges;
uniform float u_marginLeft;
uniform float u_marginRight;
uniform float u_marginTop;
uniform float u_marginBottom;
uniform float u_grainMixer;
uniform float u_grainOverlay;

in vec2 v_imageUV;

out vec4 fragColor;

${P}
${L}
${me}

float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

float getUvFrame(vec2 uv, float softness) {
  float aax = 2. * fwidth(uv.x);
  float aay = 2. * fwidth(uv.y);
  float left   = smoothstep(0., aax + softness, uv.x);
  float right  = 1. - smoothstep(1. - softness - aax, 1., uv.x);
  float bottom = smoothstep(0., aay + softness, uv.y);
  float top    = 1. - smoothstep(1. - softness - aay, 1., uv.y);
  return left * right * bottom * top;
}

const int MAX_RADIUS = 50;
vec4 samplePremultiplied(sampler2D tex, vec2 uv) {
  vec4 c = texture(tex, uv);
  c.rgb *= c.a;
  return c;
}
vec4 getBlur(sampler2D tex, vec2 uv, vec2 texelSize, vec2 dir, float sigma) {
  if (sigma <= .5) return texture(tex, uv);
  int radius = int(min(float(MAX_RADIUS), ceil(3.0 * sigma)));

  float twoSigma2 = 2.0 * sigma * sigma;
  float gaussianNorm = 1.0 / sqrt(TWO_PI * sigma * sigma);

  vec4 sum = samplePremultiplied(tex, uv) * gaussianNorm;
  float weightSum = gaussianNorm;

  for (int i = 1; i <= MAX_RADIUS; i++) {
    if (i > radius) break;

    float x = float(i);
    float w = exp(-(x * x) / twoSigma2) * gaussianNorm;

    vec2 offset = dir * texelSize * x;
    vec4 s1 = samplePremultiplied(tex, uv + offset);
    vec4 s2 = samplePremultiplied(tex, uv - offset);

    sum += (s1 + s2) * w;
    weightSum += 2.0 * w;
  }

  vec4 result = sum / weightSum;
  if (result.a > 0.) {
    result.rgb /= result.a;
  }

  return result;
}

vec2 rotateAspect(vec2 p, float a, float aspect) {
  p.x *= aspect;
  p = rotate(p, a);
  p.x /= aspect;
  return p;
}

float smoothFract(float x) {
  float f = fract(x);
  float w = fwidth(x);

  float edge = abs(f - 0.5) - 0.5;
  float band = smoothstep(-w, w, edge);

  return mix(f, 1.0 - f, band);
}

void main() {

  float patternRotation = -u_angle * PI / 180.;
  float patternSize = mix(200., 5., u_size);

  vec2 uv = v_imageUV;

  vec2 uvMask = gl_FragCoord.xy / u_resolution.xy;
  vec2 sw = vec2(.005);
  vec4 margins = vec4(u_marginLeft, u_marginTop, u_marginRight, u_marginBottom);
  float mask =
  smoothstep(margins[0], margins[0] + sw.x, uvMask.x + sw.x) *
  smoothstep(margins[2], margins[2] + sw.x, 1.0 - uvMask.x + sw.x) *
  smoothstep(margins[1], margins[1] + sw.y, uvMask.y + sw.y) *
  smoothstep(margins[3], margins[3] + sw.y, 1.0 - uvMask.y + sw.y);
  float maskOuter =
  smoothstep(margins[0] - sw.x, margins[0], uvMask.x + sw.x) *
  smoothstep(margins[2] - sw.x, margins[2], 1.0 - uvMask.x + sw.x) *
  smoothstep(margins[1] - sw.y, margins[1], uvMask.y + sw.y) *
  smoothstep(margins[3] - sw.y, margins[3], 1.0 - uvMask.y + sw.y);
  float maskStroke = maskOuter - mask;
  float maskInner =
  smoothstep(margins[0] - 2. * sw.x, margins[0], uvMask.x) *
  smoothstep(margins[2] - 2. * sw.x, margins[2], 1.0 - uvMask.x) *
  smoothstep(margins[1] - 2. * sw.y, margins[1], uvMask.y) *
  smoothstep(margins[3] - 2. * sw.y, margins[3], 1.0 - uvMask.y);
  float maskStrokeInner = maskInner - mask;

  uv -= .5;
  uv *= patternSize;
  uv = rotateAspect(uv, patternRotation, u_imageAspectRatio);

  float curve = 0.;
  float patternY = uv.y / u_imageAspectRatio;
  if (u_shape > 4.5) {
    // pattern
    curve = .5 + .5 * sin(.5 * PI * uv.x) * cos(.5 * PI * patternY);
  } else if (u_shape > 3.5) {
    // zigzag
    curve = 10. * abs(fract(.1 * patternY) - .5);
  } else if (u_shape > 2.5) {
    // wave
    curve = 4. * sin(.23 * patternY);
  } else if (u_shape > 1.5) {
    // lines irregular
    curve = .5 + .5 * sin(.5 * uv.x) * sin(1.7 * uv.x);
  } else {
    // lines
  }

  vec2 UvToFract = uv + curve;
  vec2 fractOrigUV = fract(uv);
  vec2 floorOrigUV = floor(uv);

  float x = smoothFract(UvToFract.x);
  float xNonSmooth = fract(UvToFract.x) + .0001;

  float highlightsWidth = 2. * max(.001, fwidth(UvToFract.x));
  highlightsWidth += 2. * maskStrokeInner;
  float highlights = smoothstep(0., highlightsWidth, xNonSmooth);
  highlights *= smoothstep(1., 1. - highlightsWidth, xNonSmooth);
  highlights = 1. - highlights;
  highlights *= u_highlights;
  highlights = clamp(highlights, 0., 1.);
  highlights *= mask;

  float shadows = pow(x, 1.3);
  float distortion = 0.;
  float fadeX = 1.;
  float frameFade = 0.;

  float aa = fwidth(xNonSmooth);
  aa = max(aa, fwidth(uv.x));
  aa = max(aa, fwidth(UvToFract.x));
  aa = max(aa, .0001);

  if (u_distortionShape == 1.) {
    distortion = -pow(1.5 * x, 3.);
    distortion += (.5 - u_shift);

    frameFade = pow(1.5 * x, 3.);
    aa = max(.2, aa);
    aa += mix(.2, 0., u_size);
    fadeX = smoothstep(0., aa, xNonSmooth) * smoothstep(1., 1. - aa, xNonSmooth);
    distortion = mix(.5, distortion, fadeX);
  } else if (u_distortionShape == 2.) {
    distortion = 2. * pow(x, 2.);
    distortion -= (.5 + u_shift);

    frameFade = pow(abs(x - .5), 4.);
    aa = max(.2, aa);
    aa += mix(.2, 0., u_size);
    fadeX = smoothstep(0., aa, xNonSmooth) * smoothstep(1., 1. - aa, xNonSmooth);
    distortion = mix(.5, distortion, fadeX);
    frameFade = mix(1., frameFade, .5 * fadeX);
  } else if (u_distortionShape == 3.) {
    distortion = pow(2. * (xNonSmooth - .5), 6.);
    distortion -= .25;
    distortion -= u_shift;

    frameFade = 1. - 2. * pow(abs(x - .4), 2.);
    aa = .15;
    aa += mix(.1, 0., u_size);
    fadeX = smoothstep(0., aa, xNonSmooth) * smoothstep(1., 1. - aa, xNonSmooth);
    frameFade = mix(1., frameFade, fadeX);

  } else if (u_distortionShape == 4.) {
    x = xNonSmooth;
    distortion = sin((x + .25) * TWO_PI);
    shadows = .5 + .5 * asin(distortion) / (.5 * PI);
    distortion *= .5;
    distortion -= u_shift;
    frameFade = .5 + .5 * sin(x * TWO_PI);
  } else if (u_distortionShape == 5.) {
    distortion -= pow(abs(x), .2) * x;
    distortion += .33;
    distortion -= 3. * u_shift;
    distortion *= .33;

    frameFade = .3 * (smoothstep(.0, 1., x));
    shadows = pow(x, 2.5);

    aa = max(.1, aa);
    aa += mix(.1, 0., u_size);
    fadeX = smoothstep(0., aa, xNonSmooth) * smoothstep(1., 1. - aa, xNonSmooth);
    distortion *= fadeX;
  }

  vec2 dudx = dFdx(v_imageUV);
  vec2 dudy = dFdy(v_imageUV);
  vec2 grainUV = v_imageUV - .5;
  grainUV *= (.8 / vec2(length(dudx), length(dudy)));
  grainUV += .5;
  if (u_grainMixer > 0.) {
    float grain = valueNoise(grainUV);
    grain = smoothstep(.4, .7, grain);
    grain *= u_grainMixer;
    distortion = mix(distortion, 0., grain);
  }

  shadows = min(shadows, 1.);
  shadows += maskStrokeInner;
  shadows *= mask;
  shadows = min(shadows, 1.);
  shadows *= pow(u_shadows, 2.);
  shadows = clamp(shadows, 0., 1.);

  distortion *= 3. * u_distortion;
  frameFade *= u_distortion;

  fractOrigUV.x += distortion;
  floorOrigUV = rotateAspect(floorOrigUV, -patternRotation, u_imageAspectRatio);
  fractOrigUV = rotateAspect(fractOrigUV, -patternRotation, u_imageAspectRatio);

  uv = (floorOrigUV + fractOrigUV) / patternSize;
  uv += pow(maskStroke, 4.);

  uv += vec2(.5);

  uv = mix(v_imageUV, uv, smoothstep(0., .7, mask));
  float blur = mix(0., 50., u_blur);
  blur = mix(0., blur, smoothstep(.5, 1., mask));

  float edgeDistortion = mix(.0, .04, u_edges);
  edgeDistortion += .06 * frameFade * u_edges;
  edgeDistortion *= mask;
  float frame = getUvFrame(uv, edgeDistortion);

  float stretch = 1. - smoothstep(0., .5, xNonSmooth) * smoothstep(1., 1. - .5, xNonSmooth);
  stretch = pow(stretch, 2.);
  stretch *= mask;
  stretch *= getUvFrame(uv, .1 + .05 * mask * frameFade);
  uv.y = mix(uv.y, .5, u_stretch * stretch);

  vec4 image = getBlur(u_image, uv, 1. / u_resolution / u_pixelRatio, vec2(0., 1.), blur);
  image.rgb *= image.a;
  vec4 backColor = u_colorBack;
  backColor.rgb *= backColor.a;
  vec4 highlightColor = u_colorHighlight;
  highlightColor.rgb *= highlightColor.a;
  vec4 shadowColor = u_colorShadow;

  vec3 color = highlightColor.rgb * highlights;
  float opacity = highlightColor.a * highlights;

  shadows = mix(shadows * shadowColor.a, 0., highlights);
  color = mix(color, shadowColor.rgb * shadowColor.a, .5 * shadows);
  color += .5 * pow(shadows, .5) * shadowColor.rgb;
  opacity += shadows;
  color = clamp(color, vec3(0.), vec3(1.));
  opacity = clamp(opacity, 0., 1.);

  color += image.rgb * (1. - opacity) * frame;
  opacity += image.a * (1. - opacity) * frame;

  color += backColor.rgb * (1. - opacity);
  opacity += backColor.a * (1. - opacity);

  if (u_grainOverlay > 0.) {
    float grainOverlay = valueNoise(rotate(grainUV, 1.) + vec2(3.));
    grainOverlay = mix(grainOverlay, valueNoise(rotate(grainUV, 2.) + vec2(-1.)), .5);
    grainOverlay = pow(grainOverlay, 1.3);

    float grainOverlayV = grainOverlay * 2. - 1.;
    vec3 grainOverlayColor = vec3(step(0., grainOverlayV));
    float grainOverlayStrength = u_grainOverlay * abs(grainOverlayV);
    grainOverlayStrength = pow(grainOverlayStrength, .8);
    grainOverlayStrength *= mask;
    color = mix(color, grainOverlayColor, .35 * grainOverlayStrength);

    opacity += .5 * grainOverlayStrength;
  }
  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`,it={lines:1,linesIrregular:2,wave:3,zigzag:4,pattern:5},st={prism:1,lens:2,contour:3,cascade:4,flat:5};var nt=`#version 300 es
precision mediump float;

uniform vec2 u_resolution;
uniform float u_pixelRatio;
uniform float u_originX;
uniform float u_originY;
uniform float u_fit;

uniform float u_scale;
uniform float u_rotation;
uniform float u_offsetX;
uniform float u_offsetY;

uniform vec4 u_colorFront;
uniform vec4 u_colorBack;
uniform vec4 u_colorHighlight;

uniform sampler2D u_image;
uniform float u_imageAspectRatio;

uniform float u_type;
uniform float u_pxSize;
uniform bool u_originalColors;
uniform bool u_inverted;
uniform float u_colorSteps;

out vec4 fragColor;


${me}
${P}

float getUvFrame(vec2 uv, vec2 pad) {
  float aa = 0.0001;

  float left   = smoothstep(-pad.x, -pad.x + aa, uv.x);
  float right  = smoothstep(1.0 + pad.x, 1.0 + pad.x - aa, uv.x);
  float bottom = smoothstep(-pad.y, -pad.y + aa, uv.y);
  float top    = smoothstep(1.0 + pad.y, 1.0 + pad.y - aa, uv.y);

  return left * right * bottom * top;
}

vec2 getImageUV(vec2 uv) {
  vec2 boxOrigin = vec2(.5 - u_originX, u_originY - .5);
  float r = u_rotation * PI / 180.;
  mat2 graphicRotation = mat2(cos(r), sin(r), -sin(r), cos(r));
  vec2 graphicOffset = vec2(-u_offsetX, u_offsetY);

  vec2 imageBoxSize;
  if (u_fit == 1.) { // contain
    imageBoxSize.x = min(u_resolution.x / u_imageAspectRatio, u_resolution.y) * u_imageAspectRatio;
  } else if (u_fit == 2.) { // cover
    imageBoxSize.x = max(u_resolution.x / u_imageAspectRatio, u_resolution.y) * u_imageAspectRatio;
  } else {
    imageBoxSize.x = min(10.0, 10.0 / u_imageAspectRatio * u_imageAspectRatio);
  }
  imageBoxSize.y = imageBoxSize.x / u_imageAspectRatio;
  vec2 imageBoxScale = u_resolution.xy / imageBoxSize;

  vec2 imageUV = uv;
  imageUV *= imageBoxScale;
  imageUV += boxOrigin * (imageBoxScale - 1.);
  imageUV += graphicOffset;
  imageUV /= u_scale;
  imageUV.x *= u_imageAspectRatio;
  imageUV = graphicRotation * imageUV;
  imageUV.x /= u_imageAspectRatio;

  imageUV += .5;
  imageUV.y = 1. - imageUV.y;

  return imageUV;
}

const int bayer2x2[4] = int[4](0, 2, 3, 1);
const int bayer4x4[16] = int[16](
0, 8, 2, 10,
12, 4, 14, 6,
3, 11, 1, 9,
15, 7, 13, 5
);

const int bayer8x8[64] = int[64](
0, 32, 8, 40, 2, 34, 10, 42,
48, 16, 56, 24, 50, 18, 58, 26,
12, 44, 4, 36, 14, 46, 6, 38,
60, 28, 52, 20, 62, 30, 54, 22,
3, 35, 11, 43, 1, 33, 9, 41,
51, 19, 59, 27, 49, 17, 57, 25,
15, 47, 7, 39, 13, 45, 5, 37,
63, 31, 55, 23, 61, 29, 53, 21
);

float getBayerValue(vec2 uv, int size) {
  ivec2 pos = ivec2(fract(uv / float(size)) * float(size));
  int index = pos.y * size + pos.x;

  if (size == 2) {
    return float(bayer2x2[index]) / 4.0;
  } else if (size == 4) {
    return float(bayer4x4[index]) / 16.0;
  } else if (size == 8) {
    return float(bayer8x8[index]) / 64.0;
  }
  return 0.0;
}


void main() {

  float pxSize = u_pxSize * u_pixelRatio;
  vec2 pxSizeUV = gl_FragCoord.xy - .5 * u_resolution;
  pxSizeUV /= pxSize;
  vec2 canvasPixelizedUV = (floor(pxSizeUV) + .5) * pxSize;
  vec2 normalizedUV = canvasPixelizedUV / u_resolution;

  vec2 imageUV = getImageUV(normalizedUV);
  vec2 ditheringNoiseUV = canvasPixelizedUV;
  vec4 image = texture(u_image, imageUV);
  float frame = getUvFrame(imageUV, pxSize / u_resolution);

  int type = int(floor(u_type));
  float dithering = 0.0;

  float lum = dot(vec3(.2126, .7152, .0722), image.rgb);
  lum = u_inverted ? (1. - lum) : lum;

  switch (type) {
    case 1: {
      dithering = step(hash21(ditheringNoiseUV), lum);
    } break;
    case 2:
    dithering = getBayerValue(pxSizeUV, 2);
    break;
    case 3:
    dithering = getBayerValue(pxSizeUV, 4);
    break;
    default :
    dithering = getBayerValue(pxSizeUV, 8);
    break;
  }

  float colorSteps = max(floor(u_colorSteps), 1.);
  vec3 color = vec3(0.0);
  float opacity = 1.;

  dithering -= .5;
  float brightness = clamp(lum + dithering / colorSteps, 0.0, 1.0);
  brightness = mix(0.0, brightness, frame);
  brightness = mix(0.0, brightness, image.a);
  float quantLum = floor(brightness * colorSteps + 0.5) / colorSteps;
  quantLum = mix(0.0, quantLum, frame);

  if (u_originalColors == true) {
    vec3 normColor = image.rgb / max(lum, 0.001);
    color = normColor * quantLum;

    float quantAlpha = floor(image.a * colorSteps + 0.5) / colorSteps;
    opacity = mix(quantLum, 1., quantAlpha);
  } else {
    vec3 fgColor = u_colorFront.rgb * u_colorFront.a;
    float fgOpacity = u_colorFront.a;
    vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
    float bgOpacity = u_colorBack.a;
    vec3 hlColor = u_colorHighlight.rgb * u_colorHighlight.a;
    float hlOpacity = u_colorHighlight.a;

    fgColor = mix(fgColor, hlColor, step(1.02 - .02 * u_colorSteps, brightness));
    fgOpacity = mix(fgOpacity, hlOpacity, step(1.02 - .02 * u_colorSteps, brightness));

    color = fgColor * quantLum;
    opacity = fgOpacity * quantLum;
    color += bgColor * (1.0 - opacity);
    opacity += bgOpacity * (1.0 - opacity);
  }

  fragColor = vec4(color, opacity);
}
`;var bo={maxSamples:50},lt=`#version 300 es
precision mediump float;

uniform sampler2D u_image;
uniform float u_imageAspectRatio;
uniform float u_spread;
uniform float u_bias;
uniform float u_angle;
uniform float u_perspective;
uniform float u_count;
uniform float u_dispersion;
uniform float u_dispersionShift;
uniform float u_dispersionColor;
uniform float u_focusCenter;
uniform float u_focusEdges;
uniform float u_swirl;
uniform float u_noise;
uniform float u_noiseFrequency;
uniform float u_noiseOffset;
uniform float u_lensBulge;
uniform float u_lensCircle;
uniform float u_grainMixer;
uniform float u_grainOverlay;
uniform float u_imageX;
uniform float u_imageY;

in vec2 v_imageUV;

out vec4 fragColor;

${P}
${me}
${L}

float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = hash21(i);
  float b = hash21(i + vec2(1., 0.));
  float c = hash21(i + vec2(0., 1.));
  float d = hash21(i + vec2(1., 1.));
  vec2 u = f * f * (3. - 2. * f);
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float getUvFrame(vec2 uv) {
  vec2 invAA = 1. / clamp(fwidth(uv), 1e-5, .02);
  vec2 lo = clamp(uv * invAA + .5, 0., 1.);
  vec2 hi = clamp((1. - uv) * invAA + .5, 0., 1.);
  return lo.x * hi.x * lo.y * hi.y;
}

vec4 sampleOverWhite(vec2 uv) {
  vec4 img = texture(u_image, uv);
  float cover = img.a * getUvFrame(uv);
  vec3 colorOverWhite = mix(vec3(1.), img.rgb, cover);
  return vec4(colorOverWhite, cover);
}

vec3 hueColor(float hue) {
  vec3 rgb = clamp(abs(mod(hue * 6. + vec3(0., 4., 2.), 6.) - 3.) - 1., 0., 1.);
  rgb = rgb * rgb * (3. - 2. * rgb);
  return rgb;
}
                                            
float boxInradius() {
  return .5 * min(u_imageAspectRatio, 1.);
}

float boxOutradius() {
  return .5 * length(vec2(u_imageAspectRatio, 1.));
}

float spreadReach() {
  return .7 * pow(u_spread, 1.3 + 2.7 * u_spread);
}

float innerCircleMask(float radius, float inradius) {
  return 1. - smoothstep(.5 * inradius, 1.1 * inradius, radius);
}

float dispersionCurve(float t, float biasPow) {
  float mirroredT = u_bias < 0. ? 1. - t : t;
  float curved = pow(mirroredT, biasPow);
  return u_bias < 0. ? 1. - curved : curved;
}

vec2 getSpread(vec2 fromCenter, float radius, vec2 warpedUV, float edgeAA, float inradius, float outradius, float reach, out float outStrength) {
  float angleRad = radians(u_angle);
  vec2 uniformDir = vec2(cos(angleRad), sin(angleRad));

  float invInradius = 1. / inradius;
  vec2 radialDir = fromCenter * invInradius;
  float maxLen = (outradius + reach) * invInradius;
  float radialLen = radius * invInradius;
  if (radialLen > maxLen) radialDir *= maxLen / radialLen;
  vec2 spreadDir = mix(uniformDir, radialDir, u_perspective);

  float bandProximity = smoothstep(inradius * .8, inradius, radius);
  float lensCircleMaxing = bandProximity * u_lensCircle * u_lensCircle * u_lensCircle;
  spreadDir = mix(spreadDir, radialDir, lensCircleMaxing);

  vec2 warpedAbs = abs(warpedUV - .5);
  float inner = mix(1., smoothstep(0., mix(inradius, outradius, u_focusCenter), radius), u_focusCenter);
  float boxDist = max(warpedAbs.x, warpedAbs.y) * 2.;
  float outer = mix(1., 1. - min(boxDist, 1.), u_focusEdges);
  float strength = inner * outer;

  strength *= mix(1., mix(.15, .03, max(-u_lensBulge, 0.)), lensCircleMaxing);

  vec2 outside = max(warpedAbs - .5, 0.);
  float margin = max(reach * length(spreadDir) * (1. - u_lensCircle), edgeAA);
  strength *= 1. - smoothstep(0., margin, length(outside));

  outStrength = strength;
  vec2 axis = spreadDir * (reach * strength);

  if (u_noise > 0.) {
    float turn = (valueNoise(fromCenter * u_noiseFrequency * 18. + u_noiseOffset * 30.) - .5) * 2. * u_noise;
    float cs = cos(turn), sn = sin(turn);
    axis = mat2(cs, -sn, sn, cs) * axis;
  }

  axis.x /= u_imageAspectRatio;
  return axis;
}

vec2 lensWarp(vec2 fromCenter, float radius, float inradius, out float bulgeFade) {
  bulgeFade = 1.;
  if (u_lensBulge == 0. && u_lensCircle <= 0.) return fromCenter;
  if (radius < 1e-5) return fromCenter;
  
  float r = radius;

  if (u_lensBulge != 0.) {
    float rn = radius / inradius;
    float bulge = abs(u_lensBulge) * (u_lensBulge > 0. ? 1.4 : 1.2);
    if (u_lensBulge > 0.) bulgeFade = 1. - smoothstep(1.45, 1.53, rn * bulge);
    float map = u_lensBulge > 0.
      ? tan(min(rn * bulge, 1.53)) / tan(bulge)
      : atan(rn * tan(bulge)) / bulge;
    float bulgeScale = map / rn;
    fromCenter *= bulgeScale;
    r *= bulgeScale;
  }

  if (u_lensCircle > 0.) {
    vec2 dir = fromCenter / max(r, 1e-5);
    vec2 halfBox = vec2(u_imageAspectRatio, 1.) * .5;
    float rBox = min(halfBox.x / max(abs(dir.x), 1e-4), halfBox.y / max(abs(dir.y), 1e-4));
    float band = inradius * mix(.03, .2, .5 * (u_lensBulge + 1.));
    float innerEdge = inradius - band;
    float over = smoothstep(0., 1., (r - innerEdge) / band);
    float g = r + (rBox - inradius) * pow(over, 14.);
    fromCenter = dir * mix(r, g, u_lensCircle);
  }

  return fromCenter;
}

void main() {
  vec2 uv = v_imageUV;

  float invAspect = 1. / u_imageAspectRatio;
  float inradius = boxInradius();
  float outradius = boxOutradius();
  float reach = spreadReach();

  vec2 fromCenter = uv - .5;
  fromCenter.x *= u_imageAspectRatio;
  float radius = length(fromCenter);

  float bulgeFade;
  vec2 warpedFromCenter = lensWarp(fromCenter, radius, inradius, bulgeFade);
  vec2 baseUV = vec2(warpedFromCenter.x * invAspect, warpedFromCenter.y) + .5;

  vec2 baseDerivative = fwidth(baseUV);
  float edgeAA = clamp(2. * max(baseDerivative.x, baseDerivative.y), .001, .02);

  float spreadStrength;
  vec2 spreadAxis = getSpread(fromCenter, radius, baseUV, edgeAA, inradius, outradius, reach, spreadStrength);

  vec2 grainUV = vec2(0.);
  if (u_grainMixer > 0. || u_grainOverlay > 0.) {
    vec2 dudx = dFdx(v_imageUV);
    vec2 dudy = dFdy(v_imageUV);
    grainUV = (v_imageUV - .5) * (.8 / vec2(length(dudx), length(dudy))) + .5;
  }

  if (u_grainMixer > 0.) {
    float grainSeed = valueNoise(grainUV);
    vec2 jit = fract(grainSeed * vec2(157.31, 113.57)) * 2. - 1.;
    spreadAxis += jit * .3 * u_grainMixer * length(spreadAxis);
  }

  float count = floor(u_count);
  int countInteger = int(count);

  float invCount = 1. / count;
  float invSpan = 1. / max(count - 1., 1.);
  float hueBase = u_dispersionColor + .5;
  float biasPower = 1. + 2. * abs(u_bias);
  vec2 tapBias = .5 - vec2(u_imageX, u_imageY);

  float centerAmount = clamp(1. - u_dispersionShift, 0., 1.);
  float edgesAmount = clamp(1. + u_dispersionShift, 0., 1.);
  float dispersion = u_dispersion * mix(edgesAmount, centerAmount, innerCircleMask(radius, inradius));
  float dispersionPower = pow(dispersion, .8);

  float warpedRadius = length(warpedFromCenter);
  float swirlAngle = u_swirl * .4 * PI * spreadStrength * u_spread * min(1., inradius / max(warpedRadius, 1e-4));

  vec3 colorSum = vec3(0.);
  vec3 weightSum = vec3(0.);
  float coverSum = 0.;

  for (int i = 0; i < ${bo.maxSamples}; i++) {
    if (i >= countInteger) break;

    float layer = float(i);
    float hue = hueBase + layer * invCount;

    float spread = layer * invSpan;
    if (u_bias != 0.) spread = dispersionCurve(spread, biasPower);

    // mix(axis, -axis, spread) is axis scaled by the signed position along the fan
    float fanPos = 1. - 2. * spread;
    vec2 tapUV = baseUV + spreadAxis * fanPos - .5;

    if (u_swirl != 0.) {
      tapUV.x *= u_imageAspectRatio;
      tapUV = rotate(tapUV, swirlAngle * fanPos);
      tapUV.x *= invAspect;
    }

    vec4 tap = sampleOverWhite(tapUV + tapBias);
    vec3 weight = 1. - dispersionPower * hueColor(hue);

    colorSum += tap.rgb * weight;
    weightSum += weight;
    coverSum += tap.a;
  }

  vec3 color = colorSum / max(weightSum, 1e-4);
  float coverAvg = coverSum * invCount;

  float ground = min(color.r, min(color.g, color.b));
  float alpha = max(coverAvg, 1. - ground);
  vec3 premult = max(color - (1. - alpha), 0.);
  fragColor = vec4(premult, alpha) * bulgeFade;

  if (u_grainOverlay > 0.) {
    float grain = valueNoise(rotate(grainUV, 1.) + vec2(3.));
    grain = mix(grain, valueNoise(rotate(grainUV, 2.) + vec2(-1.)), .5);
    grain = pow(grain, 1.3);
    float grainV = grain * 2. - 1.;
    float grainStrength = pow(u_grainOverlay * abs(grainV), .8) * fragColor.a;
    fragColor.rgb = mix(fragColor.rgb, vec3(step(0., grainV)) * fragColor.a, .35 * grainStrength);
  }
}
`;var vo={maxColorCount:10},ft=`#version 300 es
precision highp float;

in mediump vec2 v_imageUV;
in mediump vec2 v_objectUV;
out vec4 fragColor;

uniform sampler2D u_image;
uniform float u_time;

uniform vec4 u_colorBack;
uniform vec4 u_colors[${vo.maxColorCount}];
uniform float u_colorsCount;

uniform float u_angle;
uniform float u_noise;
uniform float u_innerGlow;
uniform float u_outerGlow;
uniform float u_contour;

#define TWO_PI 6.28318530718
#define PI 3.14159265358979323846

float getImgFrame(vec2 uv, float th) {
  float frame = 1.;
  frame *= smoothstep(0., th, uv.y);
  frame *= 1. - smoothstep(1. - th, 1., uv.y);
  frame *= smoothstep(0., th, uv.x);
  frame *= 1. - smoothstep(1. - th, 1., uv.x);
  return frame;
}

float circle(vec2 uv, vec2 c, vec2 r) {
  return 1. - smoothstep(r[0], r[1], length(uv - c));
}

float lst(float edge0, float edge1, float x) {
  return clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
}

float sst(float edge0, float edge1, float x) {
  return smoothstep(edge0, edge1, x);
}

float shadowShape(vec2 uv, float t, float contour) {
  vec2 scaledUV = uv;

  // base shape tranjectory
  float posY = mix(-1., 2., t);

  // scaleX when it's moving down
  scaledUV.y -= .5;
  float mainCircleScale = sst(0., .8, posY) * lst(1.4, .9, posY);
  scaledUV *= vec2(1., 1. + 1.5 * mainCircleScale);
  scaledUV.y += .5;

  // base shape
  float innerR = .4;
  float outerR = 1. - .3 * (sst(.1, .2, t) * (1. - sst(.2, .5, t)));
  float s = circle(scaledUV, vec2(.5, posY - .2), vec2(innerR, outerR));
  float shapeSizing = sst(.2, .3, t) * sst(.6, .3, t);
  s = pow(s, 1.4);
  s *= 1.2;

  // flat gradient to take over the shadow shape
  float topFlattener = 0.;
  {
    float pos = posY - uv.y;
    float edge = 1.2;
    topFlattener = lst(-.4, 0., pos) * (1. - sst(.0, edge, pos));
    topFlattener = pow(topFlattener, 3.);
    float topFlattenerMixer = (1. - sst(.0, .3, pos));
    s = mix(topFlattener, s, topFlattenerMixer);
  }

  // apple right circle
  {
    float visibility = sst(.6, .7, t) * (1. - sst(.8, .9, t));
    float angle = -2. -t * TWO_PI;
    float rightCircle = circle(uv, vec2(.95 - .2 * cos(angle), .4 - .1 * sin(angle)), vec2(.15, .3));
    rightCircle *= visibility;
    s = mix(s, 0., rightCircle);
  }

  // apple top circle
  {
    float topCircle = circle(uv, vec2(.5, .19), vec2(.05, .25));
    topCircle += 2. * contour * circle(uv, vec2(.5, .19), vec2(.2, .5));
    float visibility = .55 * sst(.2, .3, t) * (1. - sst(.3, .45, t));
    topCircle *= visibility;
    s = mix(s, 0., topCircle);
  }

  float leafMask = circle(uv, vec2(.53, .13), vec2(.08, .19));
  leafMask = mix(leafMask, 0., 1. - sst(.4, .54, uv.x));
  leafMask = mix(0., leafMask, sst(.0, .2, uv.y));
  leafMask *= (sst(.5, 1.1, posY) * sst(1.5, 1.3, posY));
  s += leafMask;

  // apple bottom circle
  {
    float visibility = sst(.0, .4, t) * (1. - sst(.6, .8, t));
    s = mix(s, 0., visibility * circle(uv, vec2(.52, .92), vec2(.09, .25)));
  }

  // random balls that are invisible if apple logo is selected
  {
    float pos = sst(.0, .6, t) * (1. - sst(.6, 1., t));
    s = mix(s, .5, circle(uv, vec2(.0, 1.2 - .5 * pos), vec2(.1, .3)));
    s = mix(s, .0, circle(uv, vec2(1., .5 + .5 * pos), vec2(.1, .3)));

    s = mix(s, 1., circle(uv, vec2(.95, .2 + .2 * sst(.3, .4, t) * sst(.7, .5, t)), vec2(.07, .22)));
    s = mix(s, 1., circle(uv, vec2(.95, .2 + .2 * sst(.3, .4, t) * (1. - sst(.5, .7, t))), vec2(.07, .22)));
    s /= max(1e-4, sst(1., .85, uv.y));
  }

  s = clamp(0., 1., s);
  return s;
}

float blurEdge3x3(sampler2D tex, vec2 uv, vec2 dudx, vec2 dudy, float radius, float centerSample) {
  vec2 texel = 1.0 / vec2(textureSize(tex, 0));
  vec2 r = radius * texel;

  float w1 = 1.0, w2 = 2.0, w4 = 4.0;
  float norm = 16.0;
  float sum = w4 * centerSample;

  sum += w2 * textureGrad(tex, uv + vec2(0.0, -r.y), dudx, dudy).g;
  sum += w2 * textureGrad(tex, uv + vec2(0.0, r.y), dudx, dudy).g;
  sum += w2 * textureGrad(tex, uv + vec2(-r.x, 0.0), dudx, dudy).g;
  sum += w2 * textureGrad(tex, uv + vec2(r.x, 0.0), dudx, dudy).g;

  sum += w1 * textureGrad(tex, uv + vec2(-r.x, -r.y), dudx, dudy).g;
  sum += w1 * textureGrad(tex, uv + vec2(r.x, -r.y), dudx, dudy).g;
  sum += w1 * textureGrad(tex, uv + vec2(-r.x, r.y), dudx, dudy).g;
  sum += w1 * textureGrad(tex, uv + vec2(r.x, r.y), dudx, dudy).g;

  return sum / norm;
}

void main() {
  vec2 uv = v_objectUV + .5;
  uv.y = 1. - uv.y;

  vec2 imgUV = v_imageUV;
  imgUV -= .5;
  imgUV *= 0.5714285714285714;
  imgUV += .5;
  float imgSoftFrame = getImgFrame(imgUV, .03);

  vec4 img = texture(u_image, imgUV);
  vec2 dudx = dFdx(imgUV);
  vec2 dudy = dFdy(imgUV);

  if (img.a == 0.) {
    fragColor = u_colorBack;
    return;
  }

  float t = .1 * u_time;
  t -= .3;

  float tCopy = t + 1. / 3.;
  float tCopy2 = t + 2. / 3.;

  t = mod(t, 1.);
  tCopy = mod(tCopy, 1.);
  tCopy2 = mod(tCopy2, 1.);

  vec2 animationUV = imgUV - vec2(.5);
  float angle = -u_angle * PI / 180.;
  float cosA = cos(angle);
  float sinA = sin(angle);
  animationUV = vec2(
  animationUV.x * cosA - animationUV.y * sinA,
  animationUV.x * sinA + animationUV.y * cosA
  ) + vec2(.5);

  float shape = img[0];

  img[1] = blurEdge3x3(u_image, imgUV, dudx, dudy, 8., img[1]);

  float outerBlur = 1. - mix(1., img[1], shape);
  float innerBlur = mix(img[1], 0., shape);
  float contour = mix(img[2], 0., shape);

  outerBlur *= imgSoftFrame;

  float shadow = shadowShape(animationUV, t, innerBlur);
  float shadowCopy = shadowShape(animationUV, tCopy, innerBlur);
  float shadowCopy2 = shadowShape(animationUV, tCopy2, innerBlur);

  float inner = .8 + .8 * innerBlur;
  inner = mix(inner, 0., shadow);
  inner = mix(inner, 0., shadowCopy);
  inner = mix(inner, 0., shadowCopy2);

  inner *= mix(0., 2., u_innerGlow);

  inner += (u_contour * 2.) * contour;
  inner = min(1., inner);
  inner *= (1. - shape);

  float outer = 0.;
  {
    t *= 3.;
    t = mod(t - .1, 1.);

    outer = .9 * pow(outerBlur, .8);
    float y = mod(animationUV.y - t, 1.);
    float animatedMask = sst(.3, .65, y) * (1. - sst(.65, 1., y));
    animatedMask = .5 + animatedMask;
    outer *= animatedMask;
    outer *= mix(0., 5., pow(u_outerGlow, 2.));
    outer *= imgSoftFrame;
  }

  inner = pow(inner, 1.2);
  float heat = clamp(inner + outer, 0., 1.);

  heat += (.005 + .35 * u_noise) * (fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453123) - .5);

  float mixer = heat * u_colorsCount;
  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;
  float outerShape = 0.;
  for (int i = 1; i < ${vo.maxColorCount+1}; i++) {
    if (i > int(u_colorsCount)) break;
    float m = clamp(mixer - float(i - 1), 0., 1.);
    if (i == 1) {
      outerShape = m;
    }
    vec4 c = u_colors[i - 1];
    c.rgb *= c.a;
    gradient = mix(gradient, c, m);
  }

  vec3 color = gradient.rgb * outerShape;
  float opacity = gradient.a * outerShape;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1.0 - opacity);
  opacity = opacity + u_colorBack.a * (1.0 - opacity);

  color += .02 * (fract(sin(dot(uv + 1., vec2(12.9898, 78.233))) * 43758.5453123) - .5);

  fragColor = vec4(color, opacity);
}
`;function So(e){let o=document.createElement("canvas"),a=1e3;return new Promise((t,l)=>{let i=new Image;i.crossOrigin="anonymous",i.addEventListener("load",()=>{(typeof e=="string"?e.endsWith(".svg"):e.type==="image/svg+xml")&&(i.width=a,i.height=a);let c=i.naturalWidth/i.naturalHeight,r=Math.floor(a*.15),m=Math.ceil(r*2.5),s=a,d=a;c>1?d=Math.floor(a/c):s=Math.floor(a*c),o.width=s+2*m,o.height=d+2*m;let u=o.getContext("2d",{willReadFrequently:!0});if(!u)throw new Error("Failed to get canvas 2d context");u.fillStyle="white",u.fillRect(0,0,o.width,o.height),u.drawImage(i,m,m,s,d);let{width:p,height:_}=o,g=u.getImageData(0,0,p,_).data,n=p*_,f=new Uint8ClampedArray(n);for(let z=0;z<n;z++){let E=z*4,G=g[E]??0,K=g[E+1]??0,X=g[E+2]??0;f[z]=.299*G+.587*K+.114*X|0}let x=r,b=Math.max(1,Math.round(.12*r)),S=5,B=ct(f,p,_,x,3),w=ct(f,p,_,b,3),C=ct(f,p,_,S,1),V=u.createImageData(p,_),O=V.data;for(let z=0;z<n;z++){let E=z*4;O[E]=C[z]??0,O[E+1]=B[z]??0,O[E+2]=w[z]??0,O[E+3]=255}u.putImageData(V,0,0),o.toBlob(z=>{if(!z){l(new Error("Failed to create PNG blob"));return}t({blob:z})},"image/png")}),i.addEventListener("error",()=>{l(new Error("Failed to load image"))}),i.src=typeof e=="string"?e:URL.createObjectURL(e)})}function Ut(e,o,a,t){if(t<=0)return e.slice();let l=new Uint8ClampedArray(o*a),i=new Uint32Array(o*a);for(let c=0;c<a;c++){let r=0;for(let m=0;m<o;m++){let s=c*o+m,d=e[s]??0;r+=d,i[s]=r+(c>0?i[s-o]??0:0)}}for(let c=0;c<a;c++){let r=Math.max(0,c-t),m=Math.min(a-1,c+t);for(let s=0;s<o;s++){let d=Math.max(0,s-t),u=Math.min(o-1,s+t),p=m*o+u,_=m*o+(d-1),y=(r-1)*o+u,g=(r-1)*o+(d-1),n=i[p]??0,f=d>0?i[_]??0:0,x=r>0?i[y]??0:0,b=d>0&&r>0?i[g]??0:0,S=n-f-x+b,B=(u-d+1)*(m-r+1);l[c*o+s]=Math.round(S/B)}}return l}function ct(e,o,a,t,l){if(t<=0||l<=1)return Ut(e,o,a,t);let i=e,c=e;for(let r=0;r<l;r++)c=Ut(i,o,a,t),i=c;return c}var ut=`#version 300 es
precision mediump float;

uniform sampler2D u_image;

uniform vec2 u_resolution;
uniform float u_time;

uniform vec4 u_colorBack;
uniform vec4 u_colorTint;

uniform float u_softness;
uniform float u_repetition;
uniform float u_shiftRed;
uniform float u_shiftBlue;
uniform float u_distortion;
uniform float u_contour;
uniform float u_angle;

uniform float u_shape;
uniform bool u_isImage;

in vec2 v_objectUV;
in vec2 v_responsiveUV;
in vec2 v_responsiveBoxGivenSize;
in vec2 v_imageUV;

out vec4 fragColor;

${P}
${L}
${Me}

float getColorChanges(float c1, float c2, float stripe_p, vec3 w, float blur, float bump, float tint) {

  float ch = mix(c2, c1, smoothstep(.0, 2. * blur, stripe_p));

  float border = w[0];
  ch = mix(ch, c2, smoothstep(border, border + 2. * blur, stripe_p));

  if (u_isImage == true) {
    bump = smoothstep(.2, .8, bump);
  }
  border = w[0] + .4 * (1. - bump) * w[1];
  ch = mix(ch, c1, smoothstep(border, border + 2. * blur, stripe_p));

  border = w[0] + .5 * (1. - bump) * w[1];
  ch = mix(ch, c2, smoothstep(border, border + 2. * blur, stripe_p));

  border = w[0] + w[1];
  ch = mix(ch, c1, smoothstep(border, border + 2. * blur, stripe_p));

  float gradient_t = (stripe_p - w[0] - w[1]) / w[2];
  float gradient = mix(c1, c2, smoothstep(0., 1., gradient_t));
  ch = mix(ch, gradient, smoothstep(border, border + .5 * blur, stripe_p));

  // Tint color is applied with color burn blending
  ch = mix(ch, 1. - min(1., (1. - ch) / max(tint, 0.0001)), u_colorTint.a);
  return ch;
}

float getImgFrame(vec2 uv, float th) {
  float frame = 1.;
  frame *= smoothstep(0., th, uv.y);
  frame *= 1.0 - smoothstep(1. - th, 1., uv.y);
  frame *= smoothstep(0., th, uv.x);
  frame *= 1.0 - smoothstep(1. - th, 1., uv.x);
  return frame;
}

float blurEdge3x3(sampler2D tex, vec2 uv, vec2 dudx, vec2 dudy, float radius, float centerSample) {
  vec2 texel = 1.0 / vec2(textureSize(tex, 0));
  vec2 r = radius * texel;

  float w1 = 1.0, w2 = 2.0, w4 = 4.0;
  float norm = 16.0;
  float sum = w4 * centerSample;

  sum += w2 * textureGrad(tex, uv + vec2(0.0, -r.y), dudx, dudy).r;
  sum += w2 * textureGrad(tex, uv + vec2(0.0, r.y), dudx, dudy).r;
  sum += w2 * textureGrad(tex, uv + vec2(-r.x, 0.0), dudx, dudy).r;
  sum += w2 * textureGrad(tex, uv + vec2(r.x, 0.0), dudx, dudy).r;

  sum += w1 * textureGrad(tex, uv + vec2(-r.x, -r.y), dudx, dudy).r;
  sum += w1 * textureGrad(tex, uv + vec2(r.x, -r.y), dudx, dudy).r;
  sum += w1 * textureGrad(tex, uv + vec2(-r.x, r.y), dudx, dudy).r;
  sum += w1 * textureGrad(tex, uv + vec2(r.x, r.y), dudx, dudy).r;

  return sum / norm;
}

float lst(float edge0, float edge1, float x) {
  return clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
}

void main() {

  const float firstFrameOffset = 2.8;
  float t = .3 * (u_time + firstFrameOffset);

  vec2 uv = v_imageUV;
  vec2 dudx = dFdx(v_imageUV);
  vec2 dudy = dFdy(v_imageUV);
  vec4 img = textureGrad(u_image, uv, dudx, dudy);

  if (u_isImage == false) {
    uv = v_objectUV + .5;
    uv.y = 1. - uv.y;
  }

  float cycleWidth = u_repetition;
  float edge = 0.;
  float contOffset = 1.;

  vec2 rotatedUV = uv - vec2(.5);
  float angle = (-u_angle + 70.) * PI / 180.;
  float cosA = cos(angle);
  float sinA = sin(angle);
  rotatedUV = vec2(
  rotatedUV.x * cosA - rotatedUV.y * sinA,
  rotatedUV.x * sinA + rotatedUV.y * cosA
  ) + vec2(.5);

  // u_contour is applied in 2 separate ranges:
  // - 0 to .4 sets the edge hardness, saturated above .4 (both branches below)
  // - .5 to 1 warps the stripes direction along the edges, inactive below .5 (see u_contour range 2)
  if (u_isImage == true) {
    float edgeRaw = img.r;
    edge = blurEdge3x3(u_image, uv, dudx, dudy, 6., edgeRaw);
    edge = pow(edge, 1.6);
    edge *= mix(0.0, 1.0, smoothstep(0.0, 0.4, u_contour));
  } else {
    if (u_shape < 1.) {
      // full-fill on canvas
      vec2 borderUV = v_responsiveUV + .5;
      float ratio = v_responsiveBoxGivenSize.x / v_responsiveBoxGivenSize.y;
      vec2 mask = min(borderUV, 1. - borderUV);
      vec2 pixel_thickness = min(250. / v_responsiveBoxGivenSize, vec2(.5));
      float maskX = smoothstep(0.0, pixel_thickness.x, mask.x);
      float maskY = smoothstep(0.0, pixel_thickness.y, mask.y);
      maskX = pow(maskX, .25);
      maskY = pow(maskY, .25);
      edge = clamp(1. - maskX * maskY, 0., 1.);

      uv = v_responsiveUV;
      if (ratio > 1.) {
        uv.y /= ratio;
      } else {
        uv.x *= ratio;
      }
      uv += .5;
      uv.y = 1. - uv.y;

      cycleWidth *= 2.;
      contOffset = 1.5;

    } else if (u_shape < 2.) {
      // circle
      vec2 shapeUV = uv - .5;
      shapeUV *= .67;
      edge = pow(clamp(3. * length(shapeUV), 0., 1.), 18.);
    } else if (u_shape < 3.) {
      // daisy
      vec2 shapeUV = uv - .5;
      shapeUV *= 1.68;

      float r = length(shapeUV) * 2.;
      float a = atan(shapeUV.y, shapeUV.x) + .2;
      r *= (1. + .05 * sin(3. * a + 2. * t));
      float f = abs(cos(a * 3.));
      edge = smoothstep(f, f + .7, r);
      edge *= edge;

      uv *= .8;
      cycleWidth *= 1.6;

    } else if (u_shape < 4.) {
      // diamond
      vec2 shapeUV = uv - .5;
      shapeUV = rotate(shapeUV, .25 * PI);
      shapeUV *= 1.42;
      shapeUV += .5;
      vec2 mask = min(shapeUV, 1. - shapeUV);
      vec2 pixel_thickness = vec2(.15);
      float maskX = smoothstep(0.0, pixel_thickness.x, mask.x);
      float maskY = smoothstep(0.0, pixel_thickness.y, mask.y);
      maskX = pow(maskX, .25);
      maskY = pow(maskY, .25);
      edge = clamp(1. - maskX * maskY, 0., 1.);
    } else if (u_shape < 5.) {
      // metaballs
      vec2 shapeUV = uv - .5;
      shapeUV *= 1.3;
      edge = 0.;
      for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float speed = 1.5 + 2./3. * sin(fi * 12.345);
        float angle = -fi * 1.5;
        vec2 dir1 = vec2(cos(angle), sin(angle));
        vec2 dir2 = vec2(cos(angle + 1.57), sin(angle + 1.));
        vec2 traj = .4 * (dir1 * sin(t * speed + fi * 1.23) + dir2 * cos(t * (speed * 0.7) + fi * 2.17));
        float d = length(shapeUV + traj);
        edge += pow(1.0 - clamp(d, 0.0, 1.0), 4.0);
      }
      edge = 1. - smoothstep(.65, .9, edge);
      edge = pow(edge, 4.);
    }

    edge = mix(smoothstep(.9 - 2. * fwidth(edge), .9, edge), edge, smoothstep(0.0, 0.4, u_contour));

  }

  float opacity = 0.;
  if (u_isImage == true) {
    opacity = img.g;
    float frame = getImgFrame(v_imageUV, 0.);
    opacity *= frame;
  } else {
    opacity = 1. - smoothstep(.9 - 2. * fwidth(edge), .9, edge);
    if (u_shape < 2.) {
      edge = 1.2 * edge;
    } else if (u_shape < 5.) {
      edge = 1.8 * pow(edge, 1.5);
    }
  }

  float diagBLtoTR = rotatedUV.x - rotatedUV.y;
  float diagTLtoBR = rotatedUV.x + rotatedUV.y;

  vec3 color = vec3(0.);
  vec3 color1 = vec3(.98, 0.98, 1.);
  vec3 color2 = vec3(.1, .1, .1 + .1 * smoothstep(.7, 1.3, diagTLtoBR));

  vec2 grad_uv = uv - .5;

  float dist = length(grad_uv + vec2(0., .2 * diagBLtoTR));
  grad_uv = rotate(grad_uv, (.25 - .2 * diagBLtoTR) * PI);
  float direction = grad_uv.x;

  float bump = pow(1.8 * dist, 1.2);
  bump = 1. - bump;
  bump *= pow(uv.y, .3);


  float thin_strip_1_ratio = .12 / cycleWidth * (1. - .4 * bump);
  float thin_strip_2_ratio = .07 / cycleWidth * (1. + .4 * bump);
  float wide_strip_ratio = (1. - thin_strip_1_ratio - thin_strip_2_ratio);

  float thin_strip_1_width = cycleWidth * thin_strip_1_ratio;
  float thin_strip_2_width = cycleWidth * thin_strip_2_ratio;

  float noise = snoise(uv - t);

  edge += (1. - edge) * u_distortion * noise;

  direction += diagBLtoTR;
  float contour = 0.;
  direction -= 2. * noise * diagBLtoTR * (smoothstep(0., 1., edge) * (1.0 - smoothstep(0., 1., edge)));
  // u_contour range 2
  direction *= mix(1., 1. - edge, smoothstep(.5, 1., u_contour));
  direction -= 1.7 * edge * smoothstep(.5, 1., u_contour);
  direction += .2 * pow(u_contour, 4.) * (1.0 - smoothstep(0., 1., edge));

  bump *= clamp(pow(uv.y, .1), .3, 1.);
  direction *= (.1 + (1.1 - edge) * bump);

  direction *= (.4 + .6 * (1.0 - smoothstep(.5, 1., edge)));
  direction += .18 * (smoothstep(.1, .2, uv.y) * (1.0 - smoothstep(.2, .4, uv.y)));
  direction += .03 * (smoothstep(.1, .2, 1. - uv.y) * (1.0 - smoothstep(.2, .4, 1. - uv.y)));

  direction *= (.5 + .5 * pow(uv.y, 2.));
  direction *= cycleWidth;
  direction -= t;


  float colorDispersion = (1. - bump);
  colorDispersion = clamp(colorDispersion, 0., 1.);
  float dispersionRed = colorDispersion;
  dispersionRed += .03 * bump * noise;
  dispersionRed += 5. * (smoothstep(-.1, .2, uv.y) * (1.0 - smoothstep(.1, .5, uv.y))) * (smoothstep(.4, .6, bump) * (1.0 - smoothstep(.4, 1., bump)));
  dispersionRed -= diagBLtoTR;

  float dispersionBlue = colorDispersion;
  dispersionBlue *= 1.3;
  dispersionBlue += (smoothstep(0., .4, uv.y) * (1.0 - smoothstep(.1, .8, uv.y))) * (smoothstep(.4, .6, bump) * (1.0 - smoothstep(.4, .8, bump)));
  dispersionBlue -= .2 * edge;

  dispersionRed *= (u_shiftRed / 20.);
  dispersionBlue *= (u_shiftBlue / 20.);

  float blur = 0.;
  float rExtraBlur = 0.;
  float gExtraBlur = 0.;
  if (u_isImage == true) {
    float softness = 0.05 * u_softness;
    blur = softness + .5 * smoothstep(1., 10., u_repetition) * smoothstep(.0, 1., edge);
    float smallCanvasT = 1.0 - smoothstep(100., 500., min(u_resolution.x, u_resolution.y));
    blur += smallCanvasT * smoothstep(.0, 1., edge);
    rExtraBlur = softness * (0.05 + .1 * (u_shiftRed / 20.) * bump);
    gExtraBlur = softness * 0.05 / max(0.001, abs(1. - diagBLtoTR));
  } else {
    blur = u_softness / 15. + .3 * contour;
  }

  vec3 w = vec3(thin_strip_1_width, thin_strip_2_width, wide_strip_ratio);
  w[1] -= .02 * smoothstep(.0, 1., edge + bump);
  float stripe_r = fract(direction + dispersionRed);
  float r = getColorChanges(color1.r, color2.r, stripe_r, w, blur + fwidth(stripe_r) + rExtraBlur, bump, u_colorTint.r);
  float stripe_g = fract(direction);
  float g = getColorChanges(color1.g, color2.g, stripe_g, w, blur + fwidth(stripe_g) + gExtraBlur, bump, u_colorTint.g);
  float stripe_b = fract(direction - dispersionBlue);
  float b = getColorChanges(color1.b, color2.b, stripe_b, w, blur + fwidth(stripe_b), bump, u_colorTint.b);

  color = vec3(r, g, b);
  color *= opacity;

  vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
  color = color + bgColor * (1. - opacity);
  opacity = opacity + u_colorBack.a * (1. - opacity);

  ${Z}

  fragColor = vec4(color, opacity);
}
`,We={measurePerformance:!1,workingSize:512,iterations:40};function wo(e){let o=document.createElement("canvas"),a=o.getContext("2d"),t=typeof e=="string"&&e.startsWith("blob:");return new Promise((l,i)=>{if(!e||!a){i(new Error("Invalid file or canvas context"));return}let c=t&&fetch(e).then(s=>s.headers.get("Content-Type")),r=new Image;r.crossOrigin="anonymous";let m=performance.now();r.onload=async()=>{let s,d=await c;d?s=d==="image/svg+xml":typeof e=="string"?s=e.endsWith(".svg")||e.startsWith("data:image/svg+xml"):s=e.type==="image/svg+xml";let u=r.width||r.naturalWidth,p=r.height||r.naturalHeight;if(s){let D=u/p;u>p?(u=4096,p=4096/D):(p=4096,u=4096*D),r.width=u,r.height=p}let _=Math.min(u,p),g=We.workingSize/_,n=Math.round(u*g),f=Math.round(p*g);We.measurePerformance&&(console.log("[Processing Mode]"),console.log(`  Original: ${u}\xD7${p}`),console.log(`  Working: ${n}\xD7${f} (${(g*100).toFixed(1)}% scale)`),g<1&&console.log(`  Speedup: ~${Math.round(1/(g*g))}\xD7`)),o.width=u,o.height=p;let x=document.createElement("canvas");x.width=n,x.height=f;let b=x.getContext("2d");b.drawImage(r,0,0,n,f);let S=performance.now(),w=b.getImageData(0,0,n,f).data,C=new Uint8Array(n*f),V=new Uint8Array(n*f),O=0;for(let R=0,D=0;R<w.length;R+=4,D++){let Se=w[R+3]===0?0:1;C[D]=Se,O+=Se}let z=[],E=[];for(let R=0;R<f;R++)for(let D=0;D<n;D++){let q=R*n+D;if(!C[q])continue;let Se=!1;D===0||D===n-1||R===0||R===f-1?Se=!0:Se=!C[q-1]||!C[q+1]||!C[q-n]||!C[q+n]||!C[q-n-1]||!C[q-n+1]||!C[q+n-1]||!C[q+n+1],Se?(V[q]=1,z.push(q)):E.push(q)}We.measurePerformance&&(console.log(`[Mask Building] Time: ${(performance.now()-S).toFixed(2)}ms`),console.log(`  Shape pixels: ${O} / ${n*f} (${(O/(n*f)*100).toFixed(1)}%)`),console.log(`  Interior pixels: ${E.length}`),console.log(`  Boundary pixels: ${z.length}`));let G=or(C,V,new Uint32Array(E),new Uint32Array(z),n,f),K=performance.now(),X=tr(G,C,V,n,f);We.measurePerformance&&console.log(`[Poisson Solve] Time: ${(performance.now()-K).toFixed(2)}ms`);let J=0,ne;for(let R=0;R<E.length;R++){let D=E[R];X[D]>J&&(J=X[D])}let Ue=document.createElement("canvas");Ue.width=n,Ue.height=f;let Ve=Ue.getContext("2d"),ve=Ve.createImageData(n,f);for(let R=0;R<f;R++)for(let D=0;D<n;D++){let q=R*n+D,Se=q*4;if(!C[q])ve.data[Se]=255,ve.data[Se+1]=255,ve.data[Se+2]=255,ve.data[Se+3]=0;else{let Xe=255*(1-X[q]/J);ve.data[Se]=Xe,ve.data[Se+1]=Xe,ve.data[Se+2]=Xe,ve.data[Se+3]=255}}Ve.putImageData(ve,0,0),a.imageSmoothingEnabled=!0,a.imageSmoothingQuality="high",a.drawImage(Ue,0,0,n,f,0,0,u,p);let xe=a.getImageData(0,0,u,p),Ee=document.createElement("canvas");Ee.width=u,Ee.height=p;let Oe=Ee.getContext("2d");Oe.drawImage(r,0,0,u,p);let He=Oe.getImageData(0,0,u,p);for(let R=0;R<xe.data.length;R+=4){let D=He.data[R+3],q=xe.data[R+3];D===0?(xe.data[R]=255,xe.data[R+1]=0):(xe.data[R]=q===0?0:xe.data[R],xe.data[R+1]=D),xe.data[R+2]=255,xe.data[R+3]=255}a.putImageData(xe,0,0),ne=xe,o.toBlob(R=>{if(!R){i(new Error("Failed to create PNG blob"));return}if(We.measurePerformance){let D=performance.now()-m;if(console.log(`[Total Processing Time] ${D.toFixed(2)}ms`),g<1){let q=D*Math.pow(u*p/(n*f),1.5);console.log(`[Estimated time at full resolution] ~${q.toFixed(0)}ms`),console.log(`[Time saved] ~${(q-D).toFixed(0)}ms (${Math.round(q/D)}\xD7 faster)`)}}l({imageData:ne,pngBlob:R})},"image/png")},r.onerror=()=>i(new Error("Failed to load image")),r.src=typeof e=="string"?e:URL.createObjectURL(e)})}function or(e,o,a,t,l,i){let c=a.length,r=new Int32Array(c*4);for(let m=0;m<c;m++){let s=a[m],d=s%l,u=Math.floor(s/l);r[m*4+0]=d<l-1&&e[s+1]?s+1:-1,r[m*4+1]=d>0&&e[s-1]?s-1:-1,r[m*4+2]=u>0&&e[s-l]?s-l:-1,r[m*4+3]=u<i-1&&e[s+l]?s+l:-1}return{interiorPixels:a,boundaryPixels:t,pixelCount:c,neighborIndices:r}}function tr(e,o,a,t,l){let i=We.iterations,c=.01,r=new Float32Array(t*l),{interiorPixels:m,neighborIndices:s,pixelCount:d}=e,u=performance.now(),p=1.9,_=[],y=[];for(let g=0;g<d;g++){let n=m[g],f=n%t,x=Math.floor(n/t);(f+x)%2===0?_.push(g):y.push(g)}for(let g=0;g<i;g++){for(let n of _){let f=m[n],x=s[n*4+0],b=s[n*4+1],S=s[n*4+2],B=s[n*4+3],w=0;x>=0&&(w+=r[x]),b>=0&&(w+=r[b]),S>=0&&(w+=r[S]),B>=0&&(w+=r[B]);let C=(c+w)/4;r[f]=p*C+(1-p)*r[f]}for(let n of y){let f=m[n],x=s[n*4+0],b=s[n*4+1],S=s[n*4+2],B=s[n*4+3],w=0;x>=0&&(w+=r[x]),b>=0&&(w+=r[b]),S>=0&&(w+=r[S]),B>=0&&(w+=r[B]);let C=(c+w)/4;r[f]=p*C+(1-p)*r[f]}}if(We.measurePerformance){let g=performance.now()-u;console.log(`[Optimized Poisson Solver (SOR \u03C9=${p})]`),console.log(`  Working size: ${t}\xD7${l}`),console.log(`  Iterations: ${i}`),console.log(`  Time: ${g.toFixed(2)}ms`),console.log(`  Interior pixels processed: ${d}`),console.log(`  Speed: ${(i*d/(g*1e3)).toFixed(2)} Mpixels/sec`)}return r}var mt={none:0,circle:1,daisy:2,diamond:3,metaballs:4};var pt=`#version 300 es
precision mediump float;

uniform vec4 u_colorFront;
uniform vec4 u_colorBack;
uniform float u_radius;
uniform float u_contrast;

uniform sampler2D u_image;
uniform float u_imageAspectRatio;

uniform float u_size;
uniform float u_grainMixer;
uniform float u_grainOverlay;
uniform float u_grainSize;
uniform float u_grid;
uniform bool u_originalColors;
uniform bool u_inverted;
uniform float u_type;

in vec2 v_imageUV;

out vec4 fragColor;

${P}
${L}
${me}

float valueNoise(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  float x1 = mix(a, b, u.x);
  float x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

float lst(float edge0, float edge1, float x) {
  return clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
}

float sst(float edge0, float edge1, float x) {
  return smoothstep(edge0, edge1, x);
}

float getCircle(vec2 uv, float r, float baseR) {
  r = mix(.25 * baseR, 0., r);
  float d = length(uv - .5);
  float aa = fwidth(d);
  return 1. - smoothstep(r - aa, r + aa, d);
}

float getCell(vec2 uv) {
  float insideX = step(0.0, uv.x) * (1.0 - step(1.0, uv.x));
  float insideY = step(0.0, uv.y) * (1.0 - step(1.0, uv.y));
  return insideX * insideY;
}

float getCircleWithHole(vec2 uv, float r, float baseR) {
  float cell = getCell(uv);

  r = mix(.75 * baseR, 0., r);
  float rMod = mod(r, .5);

  float d = length(uv - .5);
  float aa = fwidth(d);
  float circle = 1. - smoothstep(rMod - aa, rMod + aa, d);
  if (r < .5) {
    return circle;
  } else {
    return cell - circle;
  }
}

float getGooeyBall(vec2 uv, float r, float baseR) {
  float d = length(uv - .5);
  float sizeRadius = .3;
  if (u_grid == 1.) {
    sizeRadius = .42;
  }
  sizeRadius = mix(sizeRadius * baseR, 0., r);
  d = 1. - sst(0., sizeRadius, d);

  d = pow(d, 2. + baseR);
  return d;
}

float getSoftBall(vec2 uv, float r, float baseR) {
  float d = length(uv - .5);
  float sizeRadius = clamp(baseR, 0., 1.);
  sizeRadius = mix(.5 * sizeRadius, 0., r);
  d = 1. - lst(0., sizeRadius, d);
  float powRadius = 1. - lst(0., 2., baseR);
  d = pow(d, 4. + 3. * powRadius);
  return d;
}

float getUvFrame(vec2 uv, vec2 pad) {
  float aa = 0.0001;

  float left   = smoothstep(-pad.x, -pad.x + aa, uv.x);
  float right  = smoothstep(1.0 + pad.x, 1.0 + pad.x - aa, uv.x);
  float bottom = smoothstep(-pad.y, -pad.y + aa, uv.y);
  float top    = smoothstep(1.0 + pad.y, 1.0 + pad.y - aa, uv.y);

  return left * right * bottom * top;
}

float sigmoid(float x, float k) {
  return 1.0 / (1.0 + exp(-k * (x - 0.5)));
}

float getLumAtPx(vec2 uv, float contrast) {
  vec4 tex = texture(u_image, uv);
  vec3 color = vec3(
  sigmoid(tex.r, contrast),
  sigmoid(tex.g, contrast),
  sigmoid(tex.b, contrast)
  );
  float lum = dot(vec3(0.2126, 0.7152, 0.0722), color);
  lum = mix(1., lum, tex.a);
  lum = u_inverted ? (1. - lum) : lum;
  return lum;
}

float getLumBall(vec2 p, vec2 pad, vec2 inCellOffset, float contrast, float baseR, float stepSize, out vec4 ballColor) {
  p += inCellOffset;
  vec2 uv_i = floor(p);
  vec2 uv_f = fract(p);
  vec2 samplingUV = (uv_i + .5 - inCellOffset) * pad + vec2(.5);
  float outOfFrame = getUvFrame(samplingUV, pad * stepSize);

  float lum = getLumAtPx(samplingUV, contrast);
  ballColor = texture(u_image, samplingUV);
  ballColor.rgb *= ballColor.a;
  ballColor *= outOfFrame;

  float ball = 0.;
  if (u_type == 0.) {
    // classic
    ball = getCircle(uv_f, lum, baseR);
  } else if (u_type == 1.) {
    // gooey
    ball = getGooeyBall(uv_f, lum, baseR);
  } else if (u_type == 2.) {
    // holes
    ball = getCircleWithHole(uv_f, lum, baseR);
  } else if (u_type == 3.) {
    // soft
    ball = getSoftBall(uv_f, lum, baseR);
  }

  return ball * outOfFrame;
}


void main() {

  float stepMultiplier = 1.;
  if (u_type == 0.) {
    // classic
    stepMultiplier = 2.;
  } else if (u_type == 1. || u_type == 3.) {
    // gooey & soft
    stepMultiplier = 6.;
  }

  float cellsPerSide = mix(300., 7., pow(u_size, .7));
  cellsPerSide /= stepMultiplier;
  float cellSizeY = 1. / cellsPerSide;
  vec2 pad = cellSizeY * vec2(1. / u_imageAspectRatio, 1.);
  if (u_type == 1. && u_grid == 1.) {
    // gooey diagonal grid works differently
    pad *= .7;
  }

  vec2 uv = v_imageUV;
  uv -= vec2(.5);
  uv /= pad;

  float contrast = mix(0., 15., pow(u_contrast, 1.5));
  float baseRadius = u_radius;
  if (u_originalColors == true) {
    contrast = mix(.1, 4., pow(u_contrast, 2.));
    baseRadius = 2. * pow(.5 * u_radius, .3);
  }

  float totalShape = 0.;
  vec3 totalColor = vec3(0.);
  float totalOpacity = 0.;

  vec4 ballColor;
  float shape;
  float stepSize = 1. / stepMultiplier;
  for (float x = -0.5; x < 0.5; x += stepSize) {
    for (float y = -0.5; y < 0.5; y += stepSize) {
      vec2 offset = vec2(x, y);

      if (u_grid == 1.) {
        float rowIndex = floor((y + .5) / stepSize);
        float colIndex = floor((x + .5) / stepSize);
        if (stepSize == 1.) {
          rowIndex = floor(uv.y + y + 1.);
          if (u_type == 1.) {
            colIndex = floor(uv.x + x + 1.);
          }
        }
        if (u_type == 1.) {
          if (mod(rowIndex + colIndex, 2.) == 1.) {
            continue;
          }
        } else {
          if (mod(rowIndex, 2.) == 1.) {
            offset.x += .5 * stepSize;
          }
        }
      }

      shape = getLumBall(uv, pad, offset, contrast, baseRadius, stepSize, ballColor);
      totalColor   += ballColor.rgb * shape;
      totalShape   += shape;
      totalOpacity += shape;
    }
  }

  const float eps = 1e-4;

  totalColor /= max(totalShape, eps);
  totalOpacity /= max(totalShape, eps);

  float finalShape = 0.;
  if (u_type == 0.) {
    finalShape = min(1., totalShape);
  } else if (u_type == 1.) {
    float aa = fwidth(totalShape);
    float th = .5;
    finalShape = smoothstep(th - aa, th + aa, totalShape);
  } else if (u_type == 2.) {
    finalShape = min(1., totalShape);
  } else if (u_type == 3.) {
    finalShape = totalShape;
  }

  vec2 grainSize = mix(2000., 200., u_grainSize) * vec2(1., 1. / u_imageAspectRatio);
  vec2 grainUV = v_imageUV - .5;
  grainUV *= grainSize;
  grainUV += .5;
  if (u_grainMixer > 0.) {
    float grain = valueNoise(grainUV);
    grain = smoothstep(.55, .7 + .2 * u_grainMixer, grain);
    grain *= u_grainMixer;
    finalShape = mix(finalShape, 0., grain);
  }

  vec3 color = vec3(0.);
  float opacity = 0.;

  if (u_originalColors == true) {
    color = totalColor * finalShape;
    opacity = totalOpacity * finalShape;

    vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
    color = color + bgColor * (1. - opacity);
    opacity = opacity + u_colorBack.a * (1. - opacity);
  } else {
    vec3 fgColor = u_colorFront.rgb * u_colorFront.a;
    float fgOpacity = u_colorFront.a;
    vec3 bgColor = u_colorBack.rgb * u_colorBack.a;
    float bgOpacity = u_colorBack.a;

    color = fgColor * finalShape;
    opacity = fgOpacity * finalShape;
    color += bgColor * (1. - opacity);
    opacity += bgOpacity * (1. - opacity);
  }

  if (u_grainOverlay > 0.) {
    float grainOverlay = valueNoise(rotate(grainUV, 1.) + vec2(3.));
    grainOverlay = mix(grainOverlay, valueNoise(rotate(grainUV, 2.) + vec2(-1.)), .5);
    grainOverlay = pow(grainOverlay, 1.3);

    float grainOverlayV = grainOverlay * 2. - 1.;
    vec3 grainOverlayColor = vec3(step(0., grainOverlayV));
    float grainOverlayStrength = u_grainOverlay * abs(grainOverlayV);
    grainOverlayStrength = pow(grainOverlayStrength, .8);
    color = mix(color, grainOverlayColor, .5 * grainOverlayStrength);

    opacity += .5 * grainOverlayStrength;
  }
  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`,dt={classic:0,gooey:1,holes:2,soft:3},gt={square:0,hex:1};var ht=`#version 300 es
precision mediump float;

uniform sampler2D u_image;
uniform float u_imageAspectRatio;

uniform vec4 u_colorBack;
uniform vec4 u_colorC;
uniform vec4 u_colorM;
uniform vec4 u_colorY;
uniform vec4 u_colorK;
uniform float u_size;
uniform float u_contrast;
uniform float u_grainSize;
uniform float u_grainMixer;
uniform float u_grainOverlay;
uniform float u_gridNoise;
uniform float u_softness;
uniform float u_floodC;
uniform float u_floodM;
uniform float u_floodY;
uniform float u_floodK;
uniform float u_gainC;
uniform float u_gainM;
uniform float u_gainY;
uniform float u_gainK;
uniform float u_type;
uniform sampler2D u_noiseTexture;

in vec2 v_imageUV;
out vec4 fragColor;

const float shiftC = -.5;
const float shiftM = -.25;
const float shiftY = .2;
const float shiftK = 0.;

// Precomputed sin/cos for rotation angles (15\xB0, 75\xB0, 0\xB0, 45\xB0)
const float cosC = 0.9659258;  const float sinC = 0.2588190;   // 15\xB0
const float cosM = 0.2588190;  const float sinM = 0.9659258;   // 75\xB0
const float cosY = 1.0;        const float sinY = 0.0;         // 0\xB0
const float cosK = 0.7071068;  const float sinK = 0.7071068;   // 45\xB0

${P}

vec2 randomRG(vec2 p) {
  vec2 uv = floor(p) / 100. + .5;
  return texture(u_noiseTexture, fract(uv)).rg;
}
vec3 hash23(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * vec3(0.3183099, 0.3678794, 0.3141592)) + 0.1;
  p3 += dot(p3, p3.yzx + 19.19);
  return fract(vec3(p3.x * p3.y, p3.y * p3.z, p3.z * p3.x));
}

float sst(float edge0, float edge1, float x) {
  return smoothstep(edge0, edge1, x);
}

vec3 valueNoise3(vec2 st) {
  vec2 i = floor(st);
  vec2 f = fract(st);
  vec3 a = hash23(i);
  vec3 b = hash23(i + vec2(1.0, 0.0));
  vec3 c = hash23(i + vec2(0.0, 1.0));
  vec3 d = hash23(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  vec3 x1 = mix(a, b, u.x);
  vec3 x2 = mix(c, d, u.x);
  return mix(x1, x2, u.y);
}

float getUvFrame(vec2 uv, vec2 pad) {
  float left   = smoothstep(-pad.x, 0., uv.x);
  float right  = smoothstep(1. + pad.x, 1., uv.x);
  float bottom = smoothstep(-pad.y, 0., uv.y);
  float top    = smoothstep(1. + pad.y, 1., uv.y);

  return left * right * bottom * top;
}

vec4 RGBAtoCMYK(vec4 rgba) {
  float k = 1. - max(max(rgba.r, rgba.g), rgba.b);
  float denom = 1. - k;
  vec3 cmy = vec3(0.);
  if (denom > 1e-5) {
    cmy = (1. - rgba.rgb - vec3(k)) / denom;
  }
  return vec4(cmy, k) * rgba.a;
}

vec3 applyContrast(vec3 rgb) {
  return clamp((rgb - 0.5) * u_contrast + 0.5, 0.0, 1.0);
}

// Single-component CMYK extractors with contrast built-in, alpha-aware
float getCyan(vec4 rgba) {
  vec3 c = clamp((rgba.rgb - 0.5) * u_contrast + 0.5, 0.0, 1.0);
  float maxRGB = max(max(c.r, c.g), c.b);
  return (maxRGB > 1e-5 ? (maxRGB - c.r) / maxRGB : 0.) * rgba.a;
}
float getMagenta(vec4 rgba) {
  vec3 c = clamp((rgba.rgb - 0.5) * u_contrast + 0.5, 0.0, 1.0);
  float maxRGB = max(max(c.r, c.g), c.b);
  return (maxRGB > 1e-5 ? (maxRGB - c.g) / maxRGB : 0.) * rgba.a;
}
float getYellow(vec4 rgba) {
  vec3 c = clamp((rgba.rgb - 0.5) * u_contrast + 0.5, 0.0, 1.0);
  float maxRGB = max(max(c.r, c.g), c.b);
  return (maxRGB > 1e-5 ? (maxRGB - c.b) / maxRGB : 0.) * rgba.a;
}
float getBlack(vec4 rgba) {
  vec3 c = clamp((rgba.rgb - 0.5) * u_contrast + 0.5, 0.0, 1.0);
  return (1. - max(max(c.r, c.g), c.b)) * rgba.a;
}

vec2 cellCenterPos(vec2 uv, vec2 cellOffset, float channelIdx) {
  vec2 cellCenter = floor(uv) + .5 + cellOffset;
  return cellCenter + (randomRG(cellCenter + channelIdx * 50.) - .5) * u_gridNoise;
}

vec2 gridToImageUV(vec2 cellCenter, float cosA, float sinA, float shift, vec2 pad) {
  vec2 uvGrid = mat2(cosA, -sinA, sinA, cosA) * (cellCenter - shift);
  return uvGrid * pad + 0.5;
}

void colorMask(vec2 pos, vec2 cellCenter, float rad, float transparency, float grain, float channelAddon, float channelgain, float generalComp, bool isJoined, inout float outMask) {
  float dist = length(pos - cellCenter);

  float radius = rad;
  radius *= (1. + generalComp);
  radius += (.15 + channelgain * radius);
  radius = max(0., radius);
  radius = mix(0., radius, transparency);
  radius += channelAddon;
  radius *= (1. - grain);

  float mask = 1. - sst(0., radius, dist);
  if (isJoined) {
    // ink or sharp (joined)
    mask = pow(mask, 1.2);
  } else {
    // dots (separate)
    mask = sst(.5 - .5 * u_softness, .51 + .49 * u_softness, mask);
  }

  mask *= mix(1., mix(.5, 1., 1.5 * radius), u_softness);
  outMask += mask;
}

vec3 applyInk(vec3 paper, vec3 inkColor, float cov) {
  vec3 inkEffect = mix(vec3(1.0), inkColor, clamp(cov, 0.0, 1.0));
  return paper * inkEffect;
}

void main() {
  vec2 uv = v_imageUV;

  float cellsPerSide = mix(400.0, 7.0, pow(u_size, 0.7));
  float cellSizeY = 1.0 / cellsPerSide;
  vec2 pad = cellSizeY * vec2(1.0 / u_imageAspectRatio, 1.0);
  vec2 uvGrid = (uv - .5) / pad;
  float insideImageBox = getUvFrame(uv, pad);

  float generalComp = .1 * u_softness + .1 * u_gridNoise + .1 * (1. - step(0.5, u_type)) * (1.5 - u_softness);

  vec2 uvC = mat2(cosC, sinC, -sinC, cosC) * uvGrid + shiftC;
  vec2 uvM = mat2(cosM, sinM, -sinM, cosM) * uvGrid + shiftM;
  vec2 uvY = mat2(cosY, sinY, -sinY, cosY) * uvGrid + shiftY;
  vec2 uvK = mat2(cosK, sinK, -sinK, cosK) * uvGrid + shiftK;

  vec2 grainSize = mix(2000., 200., u_grainSize) * vec2(1., 1. / u_imageAspectRatio);
  vec2 grainUV = (v_imageUV - .5) * grainSize + .5;
  // shared by the grain mixer and the grain overlay, skip it when neither is on
  vec3 noiseValues = vec3(0.);
  if (u_grainMixer > 0. || u_grainOverlay > 0.) {
    noiseValues = valueNoise3(grainUV);
  }
  float grain = sst(.55, 1., noiseValues.r);
  grain *= u_grainMixer;

  vec4 outMask = vec4(0.);
  bool isJoined = u_type > 0.5;

  if (u_type < 1.5) {
    // dots or ink: per-cell color sampling
    for (int dy = -1; dy <= 1; dy++) {
      for (int dx = -1; dx <= 1; dx++) {
        vec2 cellOffset = vec2(float(dx), float(dy));

        vec2 cellCenterC = cellCenterPos(uvC, cellOffset, 0.);
        vec4 texC = texture(u_image, gridToImageUV(cellCenterC, cosC, sinC, shiftC, pad));
        colorMask(uvC, cellCenterC, getCyan(texC), insideImageBox * texC.a, grain, u_floodC, u_gainC, generalComp, isJoined, outMask[0]);

        vec2 cellCenterM = cellCenterPos(uvM, cellOffset, 1.);
        vec4 texM = texture(u_image, gridToImageUV(cellCenterM, cosM, sinM, shiftM, pad));
        colorMask(uvM, cellCenterM, getMagenta(texM), insideImageBox * texM.a, grain, u_floodM, u_gainM, generalComp, isJoined, outMask[1]);

        vec2 cellCenterY = cellCenterPos(uvY, cellOffset, 2.);
        vec4 texY = texture(u_image, gridToImageUV(cellCenterY, cosY, sinY, shiftY, pad));
        colorMask(uvY, cellCenterY, getYellow(texY), insideImageBox * texY.a, grain, u_floodY, u_gainY, generalComp, isJoined, outMask[2]);

        vec2 cellCenterK = cellCenterPos(uvK, cellOffset, 3.);
        vec4 texK = texture(u_image, gridToImageUV(cellCenterK, cosK, sinK, shiftK, pad));
        colorMask(uvK, cellCenterK, getBlack(texK), insideImageBox * texK.a, grain, u_floodK, u_gainK, generalComp, isJoined, outMask[3]);
      }
    }
  } else {
    // sharp: direct px color sampling
    vec4 tex = texture(u_image, uv);
    tex.rgb = applyContrast(tex.rgb);
    insideImageBox *= tex.a;
    vec4 cmykOriginal = RGBAtoCMYK(tex);
    for (int dy = -1; dy <= 1; dy++) {
      for (int dx = -1; dx <= 1; dx++) {
        vec2 cellOffset = vec2(float(dx), float(dy));

        colorMask(uvC, cellCenterPos(uvC, cellOffset, 0.), cmykOriginal.x, insideImageBox, grain, u_floodC, u_gainC, generalComp, isJoined, outMask[0]);
        colorMask(uvM, cellCenterPos(uvM, cellOffset, 1.), cmykOriginal.y, insideImageBox, grain, u_floodM, u_gainM, generalComp, isJoined, outMask[1]);
        colorMask(uvY, cellCenterPos(uvY, cellOffset, 2.), cmykOriginal.z, insideImageBox, grain, u_floodY, u_gainY, generalComp, isJoined, outMask[2]);
        colorMask(uvK, cellCenterPos(uvK, cellOffset, 3.), cmykOriginal.w, insideImageBox, grain, u_floodK, u_gainK, generalComp, isJoined, outMask[3]);
      }
    }
  }

  float shape;

  float C = outMask[0];
  float M = outMask[1];
  float Y = outMask[2];
  float K = outMask[3];

  if (isJoined) {
    // ink or sharp: apply threshold for joined dots
    float th = .5;
    float sLeft = th * u_softness;
    float sRight = (1. - th) * u_softness + .01;
    C = smoothstep(th - sLeft - fwidth(C), th + sRight, C);
    M = smoothstep(th - sLeft - fwidth(M), th + sRight, M);
    Y = smoothstep(th - sLeft - fwidth(Y), th + sRight, Y);
    K = smoothstep(th - sLeft - fwidth(K), th + sRight, K);
  }

  C *= u_colorC.a;
  M *= u_colorM.a;
  Y *= u_colorY.a;
  K *= u_colorK.a;

  vec3 ink = vec3(1.);
  ink = applyInk(ink, u_colorK.rgb, K);
  ink = applyInk(ink, u_colorC.rgb, C);
  ink = applyInk(ink, u_colorM.rgb, M);
  ink = applyInk(ink, u_colorY.rgb, Y);

  shape = clamp(max(max(C, M), max(Y, K)), 0., 1.);

  vec3 color = u_colorBack.rgb * u_colorBack.a;

  float opacity = u_colorBack.a;
  color = mix(color, ink, shape);
  opacity += shape;
  opacity = clamp(opacity, 0., 1.);

  float grainOverlay = mix(noiseValues.g, noiseValues.b, .5);
  grainOverlay = pow(grainOverlay, 1.3);

  float grainOverlayV = grainOverlay * 2. - 1.;
  vec3 grainOverlayColor = vec3(step(0., grainOverlayV));
  float grainOverlayStrength = u_grainOverlay * abs(grainOverlayV);
  grainOverlayStrength = pow(grainOverlayStrength, .8);
  color = mix(color, grainOverlayColor, .5 * grainOverlayStrength);

  opacity += .5 * grainOverlayStrength;
  opacity = clamp(opacity, 0., 1.);

  fragColor = vec4(color, opacity);
}
`,vt={dots:0,ink:1,sharp:2};var xt={maxColorCount:6},_t=`#version 300 es
precision mediump float;

in mediump vec2 v_imageUV;
in mediump vec2 v_objectUV;
in mediump vec2 v_responsiveUV;
in mediump vec2 v_responsiveBoxGivenSize;
                                               
out vec4 fragColor;

uniform sampler2D u_image;
uniform float u_shape;
uniform bool u_isImage;

uniform float u_time;
uniform vec4 u_colors[${xt.maxColorCount}];
uniform float u_colorsCount;
uniform vec4 u_colorBack;
uniform vec4 u_colorInner;
uniform float u_innerDistortion;
uniform float u_outerDistortion;
uniform float u_outerGlow;
uniform float u_innerGlow;
uniform float u_offset;
uniform float u_angle;
uniform float u_size;

${P}
${L}

// 9x9 Gaussian blur on R and G channels
vec2 gaussBlur9x9RG(sampler2D tex, vec2 uv, float radius) {
  vec2 texel = 1.0 / vec2(textureSize(tex, 0));
  vec2 r = max(radius, 0.0) * texel;
  // Pascal's row 8: sum = 256, 2D norm = 65536
  const float k[9] = float[9](1.0, 8.0, 28.0, 56.0, 70.0, 56.0, 28.0, 8.0, 1.0);
  vec2 sum = vec2(0.0);

  for (int j = -4; j <= 4; ++j) {
    float wy = k[j + 4];
    for (int i = -4; i <= 4; ++i) {
      float w = k[i + 4] * wy;
      vec2 off = vec2(float(i) * r.x, float(j) * r.y);
      sum += w * texture(tex, uv + off).rg;
    }
  }

  return sum / 65536.0;
}

float sst(float a, float b, float x) {
  return smoothstep(a, b, x);
}

void main() {
  float time = u_time;

  float roundness = 0.;
  float imgAlpha = 0.;

  if (u_isImage == true) {
    // Image sampling (UV scaled inward to account for padding)
    vec2 imageUV = v_imageUV;
    imageUV -= .5;
    imageUV *= .95;
    imageUV += .5;

    // Blurred image: x = roundness, y = alpha
    vec2 blurred = gaussBlur9x9RG(u_image, imageUV, 10.);
    roundness = 1. - blurred.x;
    vec2 texelA = 1.0 / vec2(textureSize(u_image, 0));
    const float k3[3] = float[3](1.0, 2.0, 1.0);
    for (int j = -1; j <= 1; ++j) {
      for (int i = -1; i <= 1; ++i) {
        imgAlpha += k3[i + 1] * k3[j + 1] * texture(u_image, imageUV + vec2(float(i) * texelA.x, float(j) * texelA.y)).g;
      }
    }
    imgAlpha /= 16.0;
  } else {
    vec2 uv = v_objectUV + .5;
    uv.y = 1. - uv.y;
    float edge = 0.;

    if (u_shape < 1.) {
      // full-fill on canvas
      vec2 borderUV = v_responsiveUV + .5;
      vec2 mask = min(borderUV, 1. - borderUV);
      vec2 pixel_thickness = min(250. / v_responsiveBoxGivenSize, vec2(.5));
      float maskX = smoothstep(0.0, pixel_thickness.x, mask.x);
      float maskY = smoothstep(0.0, pixel_thickness.y, mask.y);
      maskX = pow(maskX, .25);
      maskY = pow(maskY, .25);
      edge = clamp(1. - maskX * maskY, 0., 1.);
    } else if (u_shape < 2.) {
      // circle
      vec2 shapeUV = uv - .5;
      shapeUV *= .67;
      edge = pow(clamp(3. * length(shapeUV), 0., 1.), 18.);
    } else if (u_shape < 3.) {
      // daisy
      vec2 shapeUV = uv - .5;
      shapeUV *= 1.68;

      float r = length(shapeUV) * 2.;
      float a = atan(shapeUV.y, shapeUV.x) + .2;
      r *= (1. + .05 * sin(3. * a + 2. * time));
      float f = abs(cos(a * 3.));
      edge = smoothstep(f, f + .7, r);
      edge *= edge;
    } else if (u_shape < 4.) {
      // diamond
      vec2 shapeUV = uv - .5;
      shapeUV = rotate(shapeUV, .25 * PI);
      shapeUV *= 1.42;
      shapeUV += .5;
      vec2 mask = min(shapeUV, 1. - shapeUV);
      vec2 pixel_thickness = vec2(.15);
      float maskX = smoothstep(0.0, pixel_thickness.x, mask.x);
      float maskY = smoothstep(0.0, pixel_thickness.y, mask.y);
      maskX = pow(maskX, .25);
      maskY = pow(maskY, .25);
      edge = clamp(1. - maskX * maskY, 0., 1.);
    } else if (u_shape < 5.) {
      // metaballs
      vec2 shapeUV = uv - .5;
      shapeUV *= 1.3;
      edge = 0.;
      for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float speed = 1.5 + 2./3. * sin(fi * 12.345);
        float angle = -fi * 1.5;
        vec2 dir1 = vec2(cos(angle), sin(angle));
        vec2 dir2 = vec2(cos(angle + 1.57), sin(angle + 1.));
        vec2 traj = .4 * (dir1 * sin(time * speed + fi * 1.23) + dir2 * cos(time * (speed * 0.7) + fi * 2.17));
        float d = length(shapeUV + traj);
        edge += pow(1.0 - clamp(d, 0.0, 1.0), 4.0);
      }
      edge = 1. - smoothstep(.65, .9, edge);
      edge = pow(edge, 4.);
    }

    imgAlpha = 1. - smoothstep(.9 - 2. * fwidth(edge), .9, edge);
    roundness = 1. - edge;
  }

// Smoke UV setup
  vec2 smokeUV = v_objectUV;
  smokeUV = rotate(smokeUV, u_angle * PI / 180.);
  smokeUV *= mix(4., 1., u_size);

  // Two swirl paths: inner (shape-masked) and outer (free), each with independent distortion
  vec2 innerUV = smokeUV;
  vec2 outerUV = smokeUV;

  // Vertical displacement \u2014 applied independently to inner and outer
  innerUV.y += u_innerDistortion * (1. - sst(0., 1., length(.4 * innerUV)));
  innerUV.y -= .4 * u_innerDistortion;
  innerUV.y += .7 * u_offset * roundness;

  outerUV.y += u_outerDistortion * (1. - sst(0., 1., length(.4 * outerUV)));
  outerUV.y -= .4 * u_outerDistortion;

  float innerSwirl = u_innerDistortion * roundness;
  float outerSwirl = u_outerDistortion;

  for (int i = 1; i < 5; i++) {
    float fi = float(i);

    float stretchIn = max(length(dFdx(innerUV)), length(dFdy(innerUV)));
    float dampenIn = 1. / (1. + stretchIn * 8.);
    float sIn = innerSwirl * dampenIn;
    innerUV.x += sIn / fi * cos(time + fi * 2.9 * innerUV.y);
    innerUV.y += sIn / fi * cos(time + fi * 1.5 * innerUV.x);

    float stretchOut = max(length(dFdx(outerUV)), length(dFdy(outerUV)));
    float dampenOut = 1. / (1. + stretchOut * 8.);
    float sOut = outerSwirl * dampenOut;
    outerUV.x += sOut / fi * cos(time + fi * 2.9 * outerUV.y);
    outerUV.y += sOut / fi * cos(time + fi * 1.5 * outerUV.x);
  }

  // Smoke shapes from swirl fields
  float innerShape = exp(-1.5 * dot(innerUV, innerUV));
  float outerShape = exp(-1.5 * dot(outerUV, outerUV));

  // Visibility masks
  float outerMask = pow(u_outerGlow, 2.) * (1. - imgAlpha);
  float innerMask = (.01 + .99 * u_innerGlow) * imgAlpha;

  innerShape *= innerMask;
  outerShape *= outerMask;

  // Color gradient
  float mixer = (innerShape + outerShape) * u_colorsCount;
  vec4 gradient = u_colors[0];
  gradient.rgb *= gradient.a;

  float smokeMask = 0.;
  for (int i = 1; i < ${xt.maxColorCount+1}; i++) {
    if (i > int(u_colorsCount)) break;

    float m = sst(0., 1., clamp(mixer - float(i - 1), 0., 1.));
    if (i == 1) smokeMask = m;

    vec4 c = u_colors[i - 1];
    c.rgb *= c.a;
    gradient = mix(gradient, c, m);
  }

  // Compositing (premultiplied alpha, front-to-back)
  vec3 color = gradient.rgb * smokeMask;
  float opacity = gradient.a * smokeMask;

  float innerOpacity = u_colorInner.a * imgAlpha;
  vec3 innerColor = u_colorInner.rgb * innerOpacity;
  color += innerColor * (1.0 - opacity);
  opacity += innerOpacity * (1.0 - opacity);

  vec3 backColor = u_colorBack.rgb * u_colorBack.a;
  color += backColor * (1.0 - opacity);
  opacity += u_colorBack.a * (1.0 - opacity);

  fragColor = vec4(color, opacity);
}
`,Ne={measurePerformance:!1,workingSize:512,iterations:32};function Co(e){let o=document.createElement("canvas"),a=o.getContext("2d"),t=typeof e=="string"&&e.startsWith("blob:");return new Promise((l,i)=>{if(!e||!a){i(new Error("Invalid file or canvas context"));return}let c=t&&fetch(e).then(s=>s.headers.get("Content-Type")),r=new Image;r.crossOrigin="anonymous";let m=performance.now();r.onload=async()=>{let s,d=await c;d?s=d==="image/svg+xml":typeof e=="string"?s=e.endsWith(".svg")||e.startsWith("data:image/svg+xml"):s=e.type==="image/svg+xml";let u=r.width||r.naturalWidth,p=r.height||r.naturalHeight;if(s){let j=u/p;u>p?(u=4096,p=4096/j):(p=4096,u=4096*j),r.width=u,r.height=p}let _=Math.min(u,p),g=Ne.workingSize/_,n=Math.round(u*g),f=Math.round(p*g);Ne.measurePerformance&&(console.log("[Processing Mode]"),console.log(`  Original: ${u}\xD7${p}`),console.log(`  Working: ${n}\xD7${f} (${(g*100).toFixed(1)}% scale)`),g<1&&console.log(`  Speedup: ~${Math.round(1/(g*g))}\xD7`)),o.width=u,o.height=p;let x=.025,b=Math.ceil(n*x),S=Math.ceil(f*x),B=n-2*b,w=f-2*S,C=document.createElement("canvas");C.width=n,C.height=f;let V=C.getContext("2d");V.drawImage(r,b,S,B,w);let O=performance.now(),E=V.getImageData(0,0,n,f).data,G=new Uint8Array(n*f),K=new Uint8Array(n*f),X=0;for(let T=0,j=0;T<E.length;T+=4,j++){let Ie=E[T+3]===0?0:1;G[j]=Ie,X+=Ie}let J=[],ne=[];for(let T=0;T<f;T++)for(let j=0;j<n;j++){let oe=T*n+j;if(!G[oe])continue;let Ie=!1;j===0||j===n-1||T===0||T===f-1?Ie=!0:Ie=!G[oe-1]||!G[oe+1]||!G[oe-n]||!G[oe+n]||!G[oe-n-1]||!G[oe-n+1]||!G[oe+n-1]||!G[oe+n+1],Ie?(K[oe]=1,J.push(oe)):ne.push(oe)}Ne.measurePerformance&&(console.log(`[Mask Building] Time: ${(performance.now()-O).toFixed(2)}ms`),console.log(`  Shape pixels: ${X} / ${n*f} (${(X/(n*f)*100).toFixed(1)}%)`),console.log(`  Interior pixels: ${ne.length}`),console.log(`  Boundary pixels: ${J.length}`));let Ue=ar(G,K,new Uint32Array(ne),new Uint32Array(J),n,f),Ve=performance.now(),ve=rr(Ue,G,K,n,f);Ne.measurePerformance&&console.log(`[Poisson Solve] Time: ${(performance.now()-Ve).toFixed(2)}ms`);let xe=0,Ee;for(let T=0;T<ne.length;T++){let j=ne[T];ve[j]>xe&&(xe=ve[j])}let Oe=document.createElement("canvas");Oe.width=n,Oe.height=f;let He=Oe.getContext("2d"),R=He.createImageData(n,f);for(let T=0;T<f;T++)for(let j=0;j<n;j++){let oe=T*n+j,Ie=oe*4;if(!G[oe])R.data[Ie]=255,R.data[Ie+1]=255,R.data[Ie+2]=255,R.data[Ie+3]=0;else{let Uo=255*(1-ve[oe]/xe);R.data[Ie]=Uo,R.data[Ie+1]=Uo,R.data[Ie+2]=Uo,R.data[Ie+3]=255}}He.putImageData(R,0,0),a.imageSmoothingEnabled=!0,a.imageSmoothingQuality="high",a.drawImage(Oe,0,0,n,f,0,0,u,p);let D=a.getImageData(0,0,u,p),q=Math.ceil(u*x),Se=Math.ceil(p*x),yo=document.createElement("canvas");yo.width=u,yo.height=p;let Xe=yo.getContext("2d");Xe.drawImage(r,q,Se,u-2*q,p-2*Se);let qa=Xe.getImageData(0,0,u,p);for(let T=0;T<D.data.length;T+=4){let j=qa.data[T+3],oe=D.data[T+3];j===0?(D.data[T]=255,D.data[T+1]=0):(D.data[T]=oe===0?0:D.data[T],D.data[T+1]=j),D.data[T+2]=255,D.data[T+3]=255}a.putImageData(D,0,0),Ee=D,o.toBlob(T=>{if(!T){i(new Error("Failed to create PNG blob"));return}if(Ne.measurePerformance){let j=performance.now()-m;if(console.log(`[Total Processing Time] ${j.toFixed(2)}ms`),g<1){let oe=j*Math.pow(u*p/(n*f),1.5);console.log(`[Estimated time at full resolution] ~${oe.toFixed(0)}ms`),console.log(`[Time saved] ~${(oe-j).toFixed(0)}ms (${Math.round(oe/j)}\xD7 faster)`)}}l({imageData:Ee,pngBlob:T})},"image/png")},r.onerror=()=>i(new Error("Failed to load image")),r.src=typeof e=="string"?e:URL.createObjectURL(e)})}function ar(e,o,a,t,l,i){let c=a.length,r=new Int32Array(c*4);for(let m=0;m<c;m++){let s=a[m],d=s%l,u=Math.floor(s/l);r[m*4+0]=d<l-1&&e[s+1]?s+1:-1,r[m*4+1]=d>0&&e[s-1]?s-1:-1,r[m*4+2]=u>0&&e[s-l]?s-l:-1,r[m*4+3]=u<i-1&&e[s+l]?s+l:-1}return{interiorPixels:a,boundaryPixels:t,pixelCount:c,neighborIndices:r}}function rr(e,o,a,t,l){let i=Ne.iterations,c=.01,r=new Float32Array(t*l),{interiorPixels:m,neighborIndices:s,pixelCount:d}=e,u=performance.now(),p=1.9,_=[],y=[];for(let n=0;n<d;n++){let f=m[n],x=f%t,b=Math.floor(f/t);(x+b)%2===0?_.push(n):y.push(n)}for(let n=0;n<i;n++){for(let f of _){let x=m[f],b=s[f*4+0],S=s[f*4+1],B=s[f*4+2],w=s[f*4+3],C=0;b>=0&&(C+=r[b]),S>=0&&(C+=r[S]),B>=0&&(C+=r[B]),w>=0&&(C+=r[w]);let V=(c+C)/4;r[x]=p*V+(1-p)*r[x]}for(let f of y){let x=m[f],b=s[f*4+0],S=s[f*4+1],B=s[f*4+2],w=s[f*4+3],C=0;b>=0&&(C+=r[b]),S>=0&&(C+=r[S]),B>=0&&(C+=r[B]),w>=0&&(C+=r[w]);let V=(c+C)/4;r[x]=p*V+(1-p)*r[x]}}let g=new Float32Array(t*l);for(let n=0;n<3;n++){g.set(r);for(let f=0;f<d;f++){let x=m[f],b=s[f*4+0],S=s[f*4+1],B=s[f*4+2],w=s[f*4+3],C=0,V=0;b>=0&&(C+=g[b],V++),S>=0&&(C+=g[S],V++),B>=0&&(C+=g[B],V++),w>=0&&(C+=g[w],V++),r[x]=V>0?(g[x]+C/V)*.5:g[x]}}if(Ne.measurePerformance){let n=performance.now()-u;console.log(`[Optimized Poisson Solver (SOR \u03C9=${p})]`),console.log(`  Working size: ${t}\xD7${l}`),console.log(`  Iterations: ${i}`),console.log(`  Time: ${n.toFixed(2)}ms`),console.log(`  Interior pixels processed: ${d}`),console.log(`  Speed: ${(i*d/(n*1e3)).toFixed(2)} Mpixels/sec`)}return r}var yt={none:0,circle:1,daisy:2,diamond:3,metaballs:4};function v(e){if(Array.isArray(e))return e.length===4?e:e.length===3?[...e,1]:eo;if(typeof e!="string")return eo;let o,a,t,l=1;if(e.startsWith("#"))[o,a,t,l]=ir(e);else if(e.startsWith("rgb")){let i=sr(e);if(i===null)return eo;[o,a,t,l]=i}else if(e.startsWith("hsl")){let i=nr(e);if(i===null)return eo;[o,a,t,l]=lr(i)}else return console.error("Unsupported color format",e),eo;return[Ao(o,0,1),Ao(a,0,1),Ao(t,0,1),Ao(l,0,1)]}function ir(e){if(e=e.replace(/^#/,""),(e.length===3||e.length===4)&&(e=e.split("").map(i=>i+i).join("")),e.length===6&&(e=e+"ff"),!/^[0-9a-f]{8}$/i.test(e))return console.warn("Invalid hex color"),eo;let o=parseInt(e.slice(0,2),16)/255,a=parseInt(e.slice(2,4),16)/255,t=parseInt(e.slice(4,6),16)/255,l=parseInt(e.slice(6,8),16)/255;return[o,a,t,l]}function sr(e){let o=e.match(/^rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+))?\s*\)$/i);return o?[parseInt(o[1]??"0")/255,parseInt(o[2]??"0")/255,parseInt(o[3]??"0")/255,o[4]===void 0?1:parseFloat(o[4])]:null}function nr(e){let o=e.match(/^hsla?\s*\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%\s*(?:,\s*([0-9.]+))?\s*\)$/i);return o?[parseInt(o[1]??"0"),parseInt(o[2]??"0"),parseInt(o[3]??"0"),o[4]===void 0?1:parseFloat(o[4])]:null}function lr(e){let[o,a,t,l]=e,i=o/360,c=a/100,r=t/100,m,s,d;if(a===0)m=s=d=r;else{let u=(y,g,n)=>(n<0&&(n+=1),n>1&&(n-=1),n<.16666666666666666?y+(g-y)*6*n:n<.5?g:n<.6666666666666666?y+(g-y)*(.6666666666666666-n)*6:y),p=r<.5?r*(1+c):r+c-r*c,_=2*r-p;m=u(_,p,i+1/3),s=u(_,p,i),d=u(_,p,i-1/3)}return[m,s,d,l]}var Ao=(e,o,a)=>Math.min(Math.max(e,o),a),eo=[.5,.5,.5,1];function le(){if(typeof window>"u")return;let e=new Image;return e.src=cr,e}var cr="data:image/png;base64,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";var xo="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";var ko={};Ka(ko,{ColorPanels:()=>ga,Dithering:()=>ca,DotGrid:()=>Nt,DotOrbit:()=>Tt,FlutedGlass:()=>wa,GemSmoke:()=>Ya,GodRays:()=>aa,GrainGradient:()=>ua,HalftoneCmyk:()=>Ea,HalftoneDots:()=>Oa,Heatmap:()=>Ia,ImageDithering:()=>ka,LensDistortion:()=>Ua,LiquidMetal:()=>Va,MeshGradient:()=>zt,Metaballs:()=>Xt,NeuroNoise:()=>Gt,PaperTexture:()=>ba,PerlinNoise:()=>Jt,PulsingBorder:()=>pa,ShaderMount:()=>A,SimplexNoise:()=>Lt,SmokeRing:()=>Dt,Spiral:()=>ia,StaticMeshGradient:()=>va,StaticRadialGradient:()=>_a,Swirl:()=>na,Voronoi:()=>$t,Warp:()=>oa,Water:()=>Aa,Waves:()=>jt,colorPanelsMeta:()=>Ze,colorPanelsPresets:()=>da,ditheringPresets:()=>la,dotGridPresets:()=>Wt,dotOrbitMeta:()=>so,dotOrbitPresets:()=>Yt,flutedGlassPresets:()=>Sa,gemSmokePresets:()=>Ga,getShaderColorFromString:()=>v,godRaysMeta:()=>fo,godRaysPresets:()=>ta,grainGradientMeta:()=>po,grainGradientPresets:()=>fa,halftoneCmykPresets:()=>Da,halftoneDotsPresets:()=>za,heatmapMeta:()=>vo,heatmapPresets:()=>Pa,imageDitheringPresets:()=>Ba,isPaperShaderElement:()=>Mo,lensDistortionMeta:()=>bo,lensDistortionPresets:()=>Fa,liquidMetalPresets:()=>Ra,meshGradientMeta:()=>io,meshGradientPresets:()=>Vt,metaballsMeta:()=>Ke,metaballsPresets:()=>Ht,neuroNoisePresets:()=>Et,paperTextureMeta:()=>$e,paperTexturePresets:()=>ya,perlinNoisePresets:()=>Kt,pulsingBorderMeta:()=>Je,pulsingBorderPresets:()=>ma,simplexNoiseMeta:()=>no,simplexNoisePresets:()=>Qt,smokeRingMeta:()=>je,smokeRingPresets:()=>Ot,spiralPresets:()=>ra,staticMeshGradientMeta:()=>go,staticMeshGradientPresets:()=>ha,staticRadialGradientMeta:()=>ho,staticRadialGradientPresets:()=>xa,swirlMeta:()=>uo,swirlPresets:()=>sa,voronoiMeta:()=>lo,voronoiPresets:()=>Zt,warpMeta:()=>co,warpPresets:()=>ea,waterPresets:()=>Ca,wavesPresets:()=>qt});var U=e=>({$$paper:!0,type:e}),Mt=e=>e,Qe=()=>{},oo=()=>{},to=e=>({current:e}),Ye=e=>[typeof e=="function"?e():e,()=>{}],Bo=e=>e(),Pt=e=>e,k=(e,o)=>({type:e,props:o});function It(e){let o=to(void 0),a=Pt(t=>{let l=e.map(i=>{if(i!=null){if(typeof i=="function"){let c=i,r=c(t);return typeof r=="function"?r:()=>{c(null)}}return i.current=t,()=>{i.current=null}}});return()=>{l.forEach(i=>i?.())}},e);return Bo(()=>e.every(t=>t==null)?null:t=>{o.current&&(o.current(),o.current=void 0),t!=null&&(o.current=a(t))},e)}function bt(e){if(e.naturalWidth<1024&&e.naturalHeight<1024){if(e.naturalWidth<1||e.naturalHeight<1)return;let o=e.naturalWidth/e.naturalHeight;e.width=Math.round(o>1?1024*o:1024),e.height=Math.round(o>1?1024:1024/o)}}async function Rt(e){let o={},a=[],t=i=>{try{return i.startsWith("/")||new URL(i),!0}catch{return!1}},l=i=>{try{return i.startsWith("/")?!1:new URL(i,window.location.origin).origin!==window.location.origin}catch{return!1}};return Object.entries(e).forEach(([i,c])=>{if(typeof c=="string"){let r=c||xo;if(!t(r)){console.warn(`Uniform "${i}" has invalid URL "${r}". Skipping image loading.`);return}let m=new Promise((s,d)=>{let u=new Image;l(r)&&(u.crossOrigin="anonymous"),u.onload=()=>{bt(u),o[i]=u,s()},u.onerror=()=>{console.error(`Could not set uniforms. Failed to load image at ${r}`),d()},u.src=r});a.push(m)}else if(c instanceof HTMLImageElement){let r=c.decode().then(()=>{bt(c),o[i]=c});a.push(r)}else o[i]=c}),await Promise.all(a),o}var A=Mt(function({fragmentShader:o,uniforms:a,webGlContextAttributes:t,speed:l=0,frame:i=0,width:c,height:r,minPixelRatio:m,maxPixelCount:s,mipmaps:d,style:u,...p},_){let[y,g]=Ye(!1),n=to(null),f=to(null),x=to(t);Qe(()=>((async()=>{let B=await Rt(a);n.current&&!f.current&&(f.current=new Te(n.current,o,B,x.current,l,i,m,s,d),g(!0))})(),()=>{f.current?.dispose(),f.current=null}),[o]),Qe(()=>{let S=!1;return(async()=>{let w=await Rt(a);S||f.current?.setUniforms(w)})(),()=>{S=!0}},[a,y]),Qe(()=>{f.current?.setSpeed(l)},[l,y]),Qe(()=>{f.current?.setMaxPixelCount(s)},[s,y]),Qe(()=>{f.current?.setMinPixelRatio(m)},[m,y]),Qe(()=>{f.current?.setFrame(i)},[i,y]);let b=It([n,_]);return k("div",{ref:b,style:c!==void 0||r!==void 0?{width:typeof c=="string"&&isNaN(+c)===!1?+c:c,height:typeof r=="string"&&isNaN(+r)===!1?+r:r,...u}:u,...p})});A.displayName="ShaderMount";function I(e,o){if(Object.keys(e).length!==Object.keys(o).length)return!1;for(let a in e){if(a==="colors"){let t=Array.isArray(e.colors),l=Array.isArray(o.colors);if(!t||!l){if(Object.is(e.colors,o.colors)===!1)return!1;continue}if(e.colors?.length!==o.colors?.length||!e.colors?.every((i,c)=>i===o.colors?.[c]))return!1;continue}if(Object.is(e[a],o[a])===!1)return!1}return!0}var Be={name:"Default",params:{...h,speed:1,frame:0,colors:["#e0eaff","#241d9a","#f75092","#9f50d3"],distortion:.8,swirl:.1,grainMixer:0,grainOverlay:0}},mr={name:"Purple",params:{...h,speed:.6,frame:0,colors:["#aaa7d7","#3c2b8e"],distortion:1,swirl:1,grainMixer:0,grainOverlay:0}},pr={name:"Beach",params:{...h,speed:.1,frame:0,colors:["#bcecf6","#00aaff","#00f7ff","#ffd447"],distortion:.8,swirl:.35,grainMixer:0,grainOverlay:0}},dr={name:"Ink",params:{...h,speed:1,frame:0,colors:["#ffffff","#000000"],distortion:1,swirl:.2,rotation:90,grainMixer:0,grainOverlay:0}},Vt=[Be,dr,mr,pr],zt=U(function({speed:o=Be.params.speed,frame:a=Be.params.frame,colors:t=Be.params.colors,distortion:l=Be.params.distortion,swirl:i=Be.params.swirl,grainMixer:c=Be.params.grainMixer,grainOverlay:r=Be.params.grainOverlay,fit:m=Be.params.fit,rotation:s=Be.params.rotation,scale:d=Be.params.scale,originX:u=Be.params.originX,originY:p=Be.params.originY,offsetX:_=Be.params.offsetX,offsetY:y=Be.params.offsetY,worldWidth:g=Be.params.worldWidth,worldHeight:n=Be.params.worldHeight,...f}){let x={u_colors:t.map(v),u_colorsCount:t.length,u_distortion:l,u_swirl:i,u_grainMixer:c,u_grainOverlay:r,u_fit:F[m],u_rotation:s,u_scale:d,u_offsetX:_,u_offsetY:y,u_originX:u,u_originY:p,u_worldWidth:g,u_worldHeight:n};return k(A,{...f,speed:o,frame:a,fragmentShader:Po,uniforms:x})},I);var _e={name:"Default",params:{...h,speed:.5,frame:0,colorBack:"#000000",colors:["#ffffff"],noiseScale:3,noiseIterations:8,radius:.25,thickness:.65,innerShape:.7,scale:.8}},gr={name:"Solar",params:{...h,speed:1,frame:0,colorBack:"#000000",colors:["#ffffff","#ffca0a","#fc6203","#fc620366"],noiseScale:2,noiseIterations:3,radius:.4,thickness:.8,innerShape:4,scale:2,offsetY:1}},hr={name:"Line",params:{...h,frame:0,colorBack:"#000000",colors:["#4540a4","#1fe8ff"],noiseScale:1.1,noiseIterations:2,radius:.38,thickness:.01,innerShape:.88,speed:4}},vr={name:"Cloud",params:{...h,frame:0,colorBack:"#81ADEC",colors:["#ffffff"],noiseScale:3,noiseIterations:10,radius:.5,thickness:.65,innerShape:.85,speed:.5,scale:2.5}},Ot=[_e,hr,gr,vr],Dt=U(function({speed:o=_e.params.speed,frame:a=_e.params.frame,colorBack:t=_e.params.colorBack,colors:l=_e.params.colors,noiseScale:i=_e.params.noiseScale,thickness:c=_e.params.thickness,radius:r=_e.params.radius,innerShape:m=_e.params.innerShape,noiseIterations:s=_e.params.noiseIterations,fit:d=_e.params.fit,scale:u=_e.params.scale,rotation:p=_e.params.rotation,originX:_=_e.params.originX,originY:y=_e.params.originY,offsetX:g=_e.params.offsetX,offsetY:n=_e.params.offsetY,worldWidth:f=_e.params.worldWidth,worldHeight:x=_e.params.worldHeight,...b}){let S={u_colorBack:v(t),u_colors:l.map(v),u_colorsCount:l.length,u_noiseScale:i,u_thickness:c,u_radius:r,u_innerShape:m,u_noiseIterations:s,u_noiseTexture:le(),u_fit:F[d],u_scale:u,u_rotation:p,u_offsetX:g,u_offsetY:n,u_originX:_,u_originY:y,u_worldWidth:f,u_worldHeight:x};return k(A,{...b,speed:o,frame:a,fragmentShader:Io,uniforms:S})},I);var ke={name:"Default",params:{...M,speed:1,frame:0,colorFront:"#ffffff",colorMid:"#47a6ff",colorBack:"#000000",brightness:.05,contrast:.3}},xr={name:"Sensation",params:{...M,speed:1,frame:0,colorFront:"#00c8ff",colorMid:"#fbff00",colorBack:"#8b42ff",brightness:.19,contrast:.12,scale:3}},_r={name:"Bloodstream",params:{...M,speed:1,frame:0,colorFront:"#ff0000",colorMid:"#ff0000",colorBack:"#ffffff",brightness:.24,contrast:.17,scale:.7}},yr={name:"Ghost",params:{...M,speed:1,frame:0,colorFront:"#ffffff",colorMid:"#000000",colorBack:"#ffffff",brightness:0,contrast:1,scale:.55}},Et=[ke,xr,_r,yr],Gt=U(function({speed:o=ke.params.speed,frame:a=ke.params.frame,colorFront:t=ke.params.colorFront,colorMid:l=ke.params.colorMid,colorBack:i=ke.params.colorBack,brightness:c=ke.params.brightness,contrast:r=ke.params.contrast,fit:m=ke.params.fit,scale:s=ke.params.scale,rotation:d=ke.params.rotation,originX:u=ke.params.originX,originY:p=ke.params.originY,offsetX:_=ke.params.offsetX,offsetY:y=ke.params.offsetY,worldWidth:g=ke.params.worldWidth,worldHeight:n=ke.params.worldHeight,...f}){let x={u_colorFront:v(t),u_colorMid:v(l),u_colorBack:v(i),u_brightness:c,u_contrast:r,u_fit:F[m],u_scale:s,u_rotation:d,u_offsetX:_,u_offsetY:y,u_originX:u,u_originY:p,u_worldWidth:g,u_worldHeight:n};return k(A,{...f,speed:o,frame:a,fragmentShader:Ro,uniforms:x})},I);var we={name:"Default",params:{...M,speed:1.5,frame:0,colorBack:"#000000",colors:["#ffc96b","#ff6200","#ff2f00","#421100","#1a0000"],size:1,sizeRange:0,spreading:1,stepsPerColor:4}},br={name:"Shine",params:{...M,speed:.1,frame:0,colors:["#ffffff","#006aff","#fff675"],colorBack:"#000000",stepsPerColor:4,size:.3,sizeRange:.2,spreading:1,scale:.4}},Sr={name:"Bubbles",params:{...M,speed:.4,frame:0,colors:["#D0D2D5"],colorBack:"#989CA4",stepsPerColor:2,size:.9,sizeRange:.7,spreading:1,scale:1.64}},wr={name:"Hallucinatory",params:{...M,speed:5,frame:0,colors:["#000000"],colorBack:"#ffe500",stepsPerColor:2,size:.65,sizeRange:0,spreading:.3,scale:.5}},Yt=[we,Sr,br,wr],Tt=U(function({speed:o=we.params.speed,frame:a=we.params.frame,colorBack:t=we.params.colorBack,colors:l=we.params.colors,size:i=we.params.size,sizeRange:c=we.params.sizeRange,spreading:r=we.params.spreading,stepsPerColor:m=we.params.stepsPerColor,fit:s=we.params.fit,scale:d=we.params.scale,rotation:u=we.params.rotation,originX:p=we.params.originX,originY:_=we.params.originY,offsetX:y=we.params.offsetX,offsetY:g=we.params.offsetY,worldWidth:n=we.params.worldWidth,worldHeight:f=we.params.worldHeight,...x}){let b={u_colorBack:v(t),u_colors:l.map(v),u_colorsCount:l.length,u_size:i,u_sizeRange:c,u_spreading:r,u_stepsPerColor:m,u_noiseTexture:le(),u_fit:F[s],u_scale:d,u_rotation:u,u_offsetX:y,u_offsetY:g,u_originX:p,u_originY:_,u_worldWidth:n,u_worldHeight:f};return k(A,{...x,speed:o,frame:a,fragmentShader:Vo,uniforms:b})},I);var pe={name:"Default",params:{...M,colorBack:"#000000",colorFill:"#ffffff",colorStroke:"#ffaa00",size:2,gapX:32,gapY:32,strokeWidth:0,sizeRange:0,opacityRange:0,shape:"circle"}},Cr={name:"Triangles",params:{...M,colorBack:"#ffffff",colorFill:"#ffffff",colorStroke:"#808080",size:5,gapX:32,gapY:32,strokeWidth:1,sizeRange:0,opacityRange:0,shape:"triangle"}},Ar={name:"Tree line",params:{...M,colorBack:"#f4fce7",colorFill:"#052e19",colorStroke:"#000000",size:8,gapX:20,gapY:90,strokeWidth:0,sizeRange:1,opacityRange:.6,shape:"circle"}},Br={name:"Wallpaper",params:{...M,colorBack:"#204030",colorFill:"#000000",colorStroke:"#bd955b",size:9,gapX:32,gapY:32,strokeWidth:1,sizeRange:0,opacityRange:0,shape:"diamond"}},Wt=[pe,Cr,Ar,Br],Nt=U(function({colorBack:o=pe.params.colorBack,colorFill:a=pe.params.colorFill,colorStroke:t=pe.params.colorStroke,size:l=pe.params.size,gapX:i=pe.params.gapX,gapY:c=pe.params.gapY,strokeWidth:r=pe.params.strokeWidth,sizeRange:m=pe.params.sizeRange,opacityRange:s=pe.params.opacityRange,shape:d=pe.params.shape,fit:u=pe.params.fit,scale:p=pe.params.scale,rotation:_=pe.params.rotation,originX:y=pe.params.originX,originY:g=pe.params.originY,offsetX:n=pe.params.offsetX,offsetY:f=pe.params.offsetY,worldWidth:x=pe.params.worldWidth,worldHeight:b=pe.params.worldHeight,maxPixelCount:S=6016*3384,...B}){let w={u_colorBack:v(o),u_colorFill:v(a),u_colorStroke:v(t),u_dotSize:l,u_gapX:i,u_gapY:c,u_strokeWidth:r,u_sizeRange:m,u_opacityRange:s,u_shape:Oo[d],u_fit:F[u],u_scale:p,u_rotation:_,u_offsetX:n,u_offsetY:f,u_originX:y,u_originY:g,u_worldWidth:x,u_worldHeight:b};return k(A,{...B,maxPixelCount:S,fragmentShader:zo,uniforms:w})},I);var Re={name:"Default",params:{...M,scale:.6,speed:.5,frame:0,colors:["#4449CF","#FFD1E0","#F94446","#FFD36B","#FFFFFF"],stepsPerColor:2,softness:0}},kr={name:"Bubblegum",params:{...M,speed:2,frame:0,colors:["#ffffff","#ff9e9e","#5f57ff","#00f7ff"],stepsPerColor:1,softness:1,scale:1.6}},Fr={name:"Spots",params:{...M,speed:.6,frame:0,colors:["#ff7b00","#f9ffeb","#320d82"],stepsPerColor:1,softness:0,scale:1}},Ur={name:"First contact",params:{...M,speed:2,frame:0,colors:["#e8cce6","#120d22","#442c44","#e6baba","#fff5f5"],stepsPerColor:2,softness:0,scale:.2}},Qt=[Re,Fr,Ur,kr],Lt=U(function({speed:o=Re.params.speed,frame:a=Re.params.frame,colors:t=Re.params.colors,stepsPerColor:l=Re.params.stepsPerColor,softness:i=Re.params.softness,fit:c=Re.params.fit,scale:r=Re.params.scale,rotation:m=Re.params.rotation,originX:s=Re.params.originX,originY:d=Re.params.originY,offsetX:u=Re.params.offsetX,offsetY:p=Re.params.offsetY,worldWidth:_=Re.params.worldWidth,worldHeight:y=Re.params.worldHeight,...g}){let n={u_colors:t.map(v),u_colorsCount:t.length,u_stepsPerColor:l,u_softness:i,u_fit:F[c],u_scale:r,u_rotation:m,u_offsetX:u,u_offsetY:p,u_originX:s,u_originY:d,u_worldWidth:_,u_worldHeight:y};return k(A,{...g,speed:o,frame:a,fragmentShader:Do,uniforms:n})},I);var Pe={name:"Default",params:{...h,scale:1,speed:1,frame:0,colorBack:"#000000",colors:["#6e33cc","#ff5500","#ffc105","#ffc800","#f585ff"],count:10,size:.83}},Mr={name:"Ink Drops",params:{...h,scale:1,speed:2,frame:0,colorBack:"#ffffff00",colors:["#000000"],count:18,size:.1}},Pr={name:"Background",params:{...h,speed:.5,frame:0,colors:["#ae00ff","#00ff95","#ffc105"],colorBack:"#2a273f",count:13,size:.81,scale:4,rotation:0,offsetX:-.3}},Ir={name:"Solar",params:{...h,speed:1,frame:0,colors:["#ffc800","#ff5500","#ffc105"],colorBack:"#102f84",count:7,size:.75,scale:1}},Ht=[Pe,Mr,Ir,Pr],Xt=U(function({speed:o=Pe.params.speed,frame:a=Pe.params.frame,colorBack:t=Pe.params.colorBack,colors:l=Pe.params.colors,size:i=Pe.params.size,count:c=Pe.params.count,fit:r=Pe.params.fit,rotation:m=Pe.params.rotation,scale:s=Pe.params.scale,originX:d=Pe.params.originX,originY:u=Pe.params.originY,offsetX:p=Pe.params.offsetX,offsetY:_=Pe.params.offsetY,worldWidth:y=Pe.params.worldWidth,worldHeight:g=Pe.params.worldHeight,...n}){let f={u_colorBack:v(t),u_colors:l.map(v),u_colorsCount:l.length,u_size:i,u_count:c,u_noiseTexture:le(),u_fit:F[r],u_rotation:m,u_scale:s,u_offsetX:p,u_offsetY:_,u_originX:d,u_originY:u,u_worldWidth:y,u_worldHeight:g};return k(A,{...n,speed:o,frame:a,fragmentShader:Eo,uniforms:f})},I);var Ce={name:"Default",params:{...M,scale:.6,colorFront:"#ffbb00",colorBack:"#000000",shape:0,frequency:.5,amplitude:.5,spacing:1.2,proportion:.1,softness:0}},Rr={name:"Groovy",params:{...M,scale:5,rotation:90,colorFront:"#fcfcee",colorBack:"#ff896b",shape:3,frequency:.2,amplitude:.25,spacing:1.17,proportion:.57,softness:0}},Vr={name:"Tangled up",params:{...M,scale:.5,rotation:0,colorFront:"#133a41",colorBack:"#c2d8b6",shape:2.07,frequency:.44,amplitude:.57,spacing:1.05,proportion:.75,softness:0}},zr={name:"Ride the wave",params:{...M,scale:1.7,rotation:0,colorFront:"#fdffe6",colorBack:"#1f1f1f",shape:2.25,frequency:.2,amplitude:1,spacing:1.25,proportion:1,softness:0}},qt=[Ce,Rr,Vr,zr],jt=U(function({colorFront:o=Ce.params.colorFront,colorBack:a=Ce.params.colorBack,shape:t=Ce.params.shape,frequency:l=Ce.params.frequency,amplitude:i=Ce.params.amplitude,spacing:c=Ce.params.spacing,proportion:r=Ce.params.proportion,softness:m=Ce.params.softness,fit:s=Ce.params.fit,scale:d=Ce.params.scale,rotation:u=Ce.params.rotation,offsetX:p=Ce.params.offsetX,offsetY:_=Ce.params.offsetY,originX:y=Ce.params.originX,originY:g=Ce.params.originY,worldWidth:n=Ce.params.worldWidth,worldHeight:f=Ce.params.worldHeight,maxPixelCount:x=6016*3384,...b}){let S={u_colorFront:v(o),u_colorBack:v(a),u_shape:t,u_frequency:l,u_amplitude:i,u_spacing:c,u_proportion:r,u_softness:m,u_fit:F[s],u_scale:d,u_rotation:u,u_offsetX:p,u_offsetY:_,u_originX:y,u_originY:g,u_worldWidth:n,u_worldHeight:f};return k(A,{...b,fragmentShader:To,uniforms:S})},I);var re={name:"Default",params:{...M,speed:.5,frame:0,colorBack:"#632ad5",colorFront:"#fccff7",proportion:.35,softness:.1,octaveCount:1,persistence:1,lacunarity:1.5}},Or={name:"Nintendo Water",params:{...M,scale:1/.2,speed:.4,frame:0,colorBack:"#2d69d4",colorFront:"#d1eefc",proportion:.42,softness:0,octaveCount:2,persistence:.55,lacunarity:1.8}},Dr={name:"Moss",params:{...M,scale:1/.15,speed:.02,frame:0,colorBack:"#05ff4a",colorFront:"#262626",proportion:.65,softness:.35,octaveCount:6,persistence:1,lacunarity:2.55}},Er={name:"Worms",params:{...M,scale:.9,speed:0,frame:0,colorBack:"#ffffff00",colorFront:"#595959",proportion:.5,softness:0,octaveCount:1,persistence:1,lacunarity:1.5}},Kt=[re,Or,Dr,Er],Jt=U(function({speed:o=re.params.speed,frame:a=re.params.frame,colorFront:t=re.params.colorFront,colorBack:l=re.params.colorBack,proportion:i=re.params.proportion,softness:c=re.params.softness,octaveCount:r=re.params.octaveCount,persistence:m=re.params.persistence,lacunarity:s,fit:d=re.params.fit,worldWidth:u=re.params.worldWidth,worldHeight:p=re.params.worldHeight,scale:_=re.params.scale,rotation:y=re.params.rotation,originX:g=re.params.originX,originY:n=re.params.originY,offsetX:f=re.params.offsetX,offsetY:x=re.params.offsetY,...b}){let S={u_colorBack:v(l),u_colorFront:v(t),u_proportion:i,u_softness:c??re.params.softness,u_octaveCount:r??re.params.octaveCount,u_persistence:m??re.params.persistence,u_lacunarity:s??re.params.lacunarity,u_fit:F[d],u_scale:_,u_rotation:y,u_offsetX:f,u_offsetY:x,u_originX:g,u_originY:n,u_worldWidth:u,u_worldHeight:p};return k(A,{...b,speed:o,frame:a,fragmentShader:Go,uniforms:S})},I);var ye={name:"Default",params:{...M,speed:.5,frame:0,colors:["#ff8247","#ffe53d"],stepsPerColor:3,colorGlow:"#ffffff",colorGap:"#2e0000",distortion:.4,gap:.04,glow:0,scale:.5}},Gr={name:"Cells",params:{...M,scale:.5,speed:.5,frame:0,colors:["#ffffff"],stepsPerColor:1,colorGlow:"#ffffff",colorGap:"#000000",distortion:.5,gap:.03,glow:.8}},Yr={name:"Bubbles",params:{...M,scale:.75,speed:.5,frame:0,colors:["#83c9fb"],stepsPerColor:1,colorGlow:"#ffffff",colorGap:"#ffffff",distortion:.4,gap:0,glow:1}},Tr={name:"Lights",params:{...M,scale:3.3,speed:.5,frame:0,colors:["#fffffffc","#bbff00","#00ffff"],colorGlow:"#ff00d0",colorGap:"#ff00d0",stepsPerColor:2,distortion:.38,gap:0,glow:1}},Zt=[ye,Tr,Gr,Yr],$t=U(function({speed:o=ye.params.speed,frame:a=ye.params.frame,colors:t=ye.params.colors,stepsPerColor:l=ye.params.stepsPerColor,colorGlow:i=ye.params.colorGlow,colorGap:c=ye.params.colorGap,distortion:r=ye.params.distortion,gap:m=ye.params.gap,glow:s=ye.params.glow,fit:d=ye.params.fit,scale:u=ye.params.scale,rotation:p=ye.params.rotation,originX:_=ye.params.originX,originY:y=ye.params.originY,offsetX:g=ye.params.offsetX,offsetY:n=ye.params.offsetY,worldWidth:f=ye.params.worldWidth,worldHeight:x=ye.params.worldHeight,...b}){let S={u_colors:t.map(v),u_colorsCount:t.length,u_stepsPerColor:l,u_colorGlow:v(i),u_colorGap:v(c),u_distortion:r,u_gap:m,u_glow:s,u_noiseTexture:le(),u_fit:F[d],u_scale:u,u_rotation:p,u_offsetX:g,u_offsetY:n,u_originX:_,u_originY:y,u_worldWidth:f,u_worldHeight:x};return k(A,{...b,speed:o,frame:a,fragmentShader:Yo,uniforms:S})},I);var de={name:"Default",params:{...M,rotation:0,speed:1,frame:0,colors:["#121212","#9470ff","#121212","#8838ff"],proportion:.45,softness:1,distortion:.25,swirl:.8,swirlIterations:10,shapeScale:.1,shape:"checks"}},Wr={name:"Cauldron Pot",params:{...M,scale:.9,rotation:160,speed:10,frame:0,colors:["#a7e58b","#324472","#0a180d"],proportion:.64,softness:1.5,distortion:.2,swirl:.86,swirlIterations:7,shapeScale:.6,shape:"edge"}},Nr={name:"Live Ink",params:{...M,scale:1.2,rotation:44,offsetY:-.3,speed:2.5,frame:0,colors:["#111314","#9faeab","#f3fee7","#f3fee7"],proportion:.05,softness:0,distortion:.25,swirl:.8,swirlIterations:10,shapeScale:.28,shape:"checks"}},Qr={name:"Kelp",params:{...M,scale:.8,rotation:50,speed:20,frame:0,colors:["#dbff8f","#404f3e","#091316"],proportion:.67,softness:0,distortion:0,swirl:.2,swirlIterations:3,shapeScale:1,shape:"stripes"}},Lr={name:"Nectar",params:{...M,scale:2,offsetY:.6,rotation:0,speed:4.2,frame:0,colors:["#151310","#d3a86b","#f0edea"],proportion:.24,softness:1,distortion:.21,swirl:.57,swirlIterations:10,shapeScale:.75,shape:"edge"}},Hr={name:"Passion",params:{...M,scale:2.5,rotation:1.35,speed:3,frame:0,colors:["#3b1515","#954751","#ffc085"],proportion:.5,softness:1,distortion:.09,swirl:.9,swirlIterations:6,shapeScale:.25,shape:"checks"}},ea=[de,Wr,Nr,Qr,Lr,Hr],oa=U(function({speed:o=de.params.speed,frame:a=de.params.frame,colors:t=de.params.colors,proportion:l=de.params.proportion,softness:i=de.params.softness,distortion:c=de.params.distortion,swirl:r=de.params.swirl,swirlIterations:m=de.params.swirlIterations,shapeScale:s=de.params.shapeScale,shape:d=de.params.shape,fit:u=de.params.fit,scale:p=de.params.scale,rotation:_=de.params.rotation,originX:y=de.params.originX,originY:g=de.params.originY,offsetX:n=de.params.offsetX,offsetY:f=de.params.offsetY,worldWidth:x=de.params.worldWidth,worldHeight:b=de.params.worldHeight,...S}){let B={u_colors:t.map(v),u_colorsCount:t.length,u_proportion:l,u_softness:i,u_distortion:c,u_swirl:r,u_swirlIterations:m,u_shapeScale:s,u_shape:No[d],u_noiseTexture:le(),u_scale:p,u_rotation:_,u_fit:F[u],u_offsetX:n,u_offsetY:f,u_originX:y,u_originY:g,u_worldWidth:x,u_worldHeight:b};return k(A,{...S,speed:o,frame:a,fragmentShader:Wo,uniforms:B})},I);var ce={name:"Default",params:{...h,offsetX:0,offsetY:-.55,colorBack:"#000000",colorBloom:"#0000ff",colors:["#a600ff6e","#6200fff0","#ffffff","#33fff5"],density:.3,spotty:.3,midIntensity:.4,midSize:.2,intensity:.8,bloom:.4,speed:.75,frame:0}},Xr={name:"Warp",params:{...h,colorBack:"#000000",colorBloom:"#222288",colors:["#ff47d4","#ff8c00","#ffffff"],density:.45,spotty:.15,midIntensity:.4,midSize:.33,intensity:.79,bloom:.4,speed:2,frame:0}},qr={name:"Linear",params:{...h,offsetX:.2,offsetY:-.8,colorBack:"#000000",colorBloom:"#eeeeee",colors:["#ffffff1f","#ffffff3d","#ffffff29"],density:.41,spotty:.25,midSize:.1,midIntensity:.75,intensity:.79,bloom:1,speed:.5,frame:0}},jr={name:"Ether",params:{...h,offsetX:-.6,colorBack:"#090f1d",colorBloom:"#ffffff",colors:["#148effa6","#c4dffebe","#232a47"],density:.03,spotty:.77,midSize:.1,midIntensity:.6,intensity:.6,bloom:.6,speed:1,frame:0}},ta=[ce,Xr,qr,jr],aa=U(function({speed:o=ce.params.speed,frame:a=ce.params.frame,colorBloom:t=ce.params.colorBloom,colorBack:l=ce.params.colorBack,colors:i=ce.params.colors,density:c=ce.params.density,spotty:r=ce.params.spotty,midIntensity:m=ce.params.midIntensity,midSize:s=ce.params.midSize,intensity:d=ce.params.intensity,bloom:u=ce.params.bloom,fit:p=ce.params.fit,scale:_=ce.params.scale,rotation:y=ce.params.rotation,originX:g=ce.params.originX,originY:n=ce.params.originY,offsetX:f=ce.params.offsetX,offsetY:x=ce.params.offsetY,worldWidth:b=ce.params.worldWidth,worldHeight:S=ce.params.worldHeight,...B}){let w={u_colorBloom:v(t),u_colorBack:v(l),u_colors:i.map(v),u_colorsCount:i.length,u_density:c,u_spotty:r,u_midIntensity:m,u_midSize:s,u_intensity:d,u_bloom:u,u_noiseTexture:le(),u_fit:F[p],u_scale:_,u_rotation:y,u_offsetX:f,u_offsetY:x,u_originX:g,u_originY:n,u_worldWidth:b,u_worldHeight:S};return k(A,{...B,speed:o,frame:a,fragmentShader:Qo,uniforms:w})},I);var ie={name:"Default",params:{...M,scale:1,colorBack:"#001429",colorFront:"#79D1FF",density:1,distortion:0,strokeWidth:.5,strokeTaper:0,strokeCap:0,noise:0,noiseFrequency:0,softness:0,speed:1,frame:0}},Kr={name:"Droplet",params:{...M,colorBack:"#effafe",colorFront:"#bf40a0",density:.9,distortion:0,strokeWidth:.75,strokeTaper:.18,strokeCap:1,noise:.74,noiseFrequency:.33,softness:.02,speed:1,frame:0}},Jr={name:"Jungle",params:{...M,scale:1.3,density:.5,colorBack:"#a0ef2a",colorFront:"#288b18",distortion:0,strokeWidth:.5,strokeTaper:0,strokeCap:0,noise:1,noiseFrequency:.25,softness:0,speed:.75,frame:0}},Zr={name:"Swirl",params:{...M,scale:.45,colorBack:"#b3e6d9",colorFront:"#1a2b4d",density:.2,distortion:0,strokeWidth:.5,strokeTaper:0,strokeCap:0,noise:0,noiseFrequency:.3,softness:.5,speed:1,frame:0}},ra=[ie,Jr,Kr,Zr],ia=U(function({speed:o=ie.params.speed,frame:a=ie.params.frame,colorBack:t=ie.params.colorBack,colorFront:l=ie.params.colorFront,density:i=ie.params.density,distortion:c=ie.params.distortion,strokeWidth:r=ie.params.strokeWidth,strokeTaper:m=ie.params.strokeTaper,strokeCap:s=ie.params.strokeCap,noiseFrequency:d=ie.params.noiseFrequency,noise:u=ie.params.noise,softness:p=ie.params.softness,fit:_=ie.params.fit,rotation:y=ie.params.rotation,scale:g=ie.params.scale,originX:n=ie.params.originX,originY:f=ie.params.originY,offsetX:x=ie.params.offsetX,offsetY:b=ie.params.offsetY,worldWidth:S=ie.params.worldWidth,worldHeight:B=ie.params.worldHeight,...w}){let C={u_colorBack:v(t),u_colorFront:v(l),u_density:i,u_distortion:c,u_strokeWidth:r,u_strokeTaper:m,u_strokeCap:s,u_noiseFrequency:d,u_noise:u,u_softness:p,u_fit:F[_],u_scale:g,u_rotation:y,u_offsetX:x,u_offsetY:b,u_originX:n,u_originY:f,u_worldWidth:S,u_worldHeight:B};return k(A,{...w,speed:o,frame:a,fragmentShader:Lo,uniforms:C})},I);var fe={name:"Default",params:{...h,speed:.32,frame:0,colorBack:"#330000",colors:["#ffd1d1","#ff8a8a","#660000"],bandCount:4,twist:.1,center:.2,proportion:.5,softness:0,noiseFrequency:.4,noise:.2}},$r={name:"Opening",params:{...h,offsetX:-.4,offsetY:1,speed:.5,frame:0,colorBack:"#ff8b61",colors:["#fefff0","#ffd8bd","#ff8b61"],bandCount:2,twist:.3,center:.2,proportion:.5,softness:0,noiseFrequency:0,noise:0,scale:1}},ei={name:"007",params:{...h,speed:1,frame:0,colorBack:"#E9E7DA",colors:["#000000"],bandCount:5,twist:.3,center:0,proportion:0,softness:0,noiseFrequency:.5,noise:0}},oi={name:"Candy",params:{...h,speed:1,frame:0,colorBack:"#ffcd66",colors:["#6bbceb","#d7b3ff","#ff9fff"],bandCount:2,twist:.15,center:.2,proportion:.5,softness:1,noiseFrequency:.5,noise:0}},sa=[fe,ei,$r,oi],na=U(function({speed:o=fe.params.speed,frame:a=fe.params.frame,colorBack:t=fe.params.colorBack,colors:l=fe.params.colors,bandCount:i=fe.params.bandCount,twist:c=fe.params.twist,center:r=fe.params.center,proportion:m=fe.params.proportion,softness:s=fe.params.softness,noiseFrequency:d=fe.params.noiseFrequency,noise:u=fe.params.noise,fit:p=fe.params.fit,rotation:_=fe.params.rotation,scale:y=fe.params.scale,originX:g=fe.params.originX,originY:n=fe.params.originY,offsetX:f=fe.params.offsetX,offsetY:x=fe.params.offsetY,worldWidth:b=fe.params.worldWidth,worldHeight:S=fe.params.worldHeight,...B}){let w={u_colorBack:v(t),u_colors:l.map(v),u_colorsCount:l.length,u_bandCount:i,u_twist:c,u_center:r,u_proportion:m,u_softness:s,u_noiseFrequency:d,u_noise:u,u_fit:F[p],u_scale:y,u_rotation:_,u_offsetX:f,u_offsetY:x,u_originX:g,u_originY:n,u_worldWidth:b,u_worldHeight:S};return k(A,{...B,speed:o,frame:a,fragmentShader:Ho,uniforms:w})},I);var Fe={name:"Default",params:{...M,speed:1,frame:0,scale:.6,colorBack:"#000000",colorFront:"#00b2ff",shape:"sphere",type:"4x4",size:2}},ti={name:"Sine Wave",params:{...M,speed:1,frame:0,colorBack:"#730d54",colorFront:"#00becc",shape:"wave",type:"4x4",size:11,scale:1.2}},ai={name:"Bugs",params:{...M,speed:1,frame:0,colorBack:"#000000",colorFront:"#008000",shape:"dots",type:"random",size:9}},ri={name:"Ripple",params:{...h,speed:1,frame:0,colorBack:"#603520",colorFront:"#c67953",shape:"ripple",type:"2x2",size:3}},ii={name:"Swirl",params:{...h,speed:1,frame:0,colorBack:"#00000000",colorFront:"#47a8e1",shape:"swirl",type:"8x8",size:2}},si={name:"Warp",params:{...h,speed:1,frame:0,colorBack:"#301c2a",colorFront:"#56ae6c",shape:"warp",type:"4x4",size:2.5}},la=[Fe,si,ti,ri,ai,ii],ca=U(function({speed:o=Fe.params.speed,frame:a=Fe.params.frame,colorBack:t=Fe.params.colorBack,colorFront:l=Fe.params.colorFront,shape:i=Fe.params.shape,type:c=Fe.params.type,pxSize:r,size:m=r===void 0?Fe.params.size:r,fit:s=Fe.params.fit,scale:d=Fe.params.scale,rotation:u=Fe.params.rotation,originX:p=Fe.params.originX,originY:_=Fe.params.originY,offsetX:y=Fe.params.offsetX,offsetY:g=Fe.params.offsetY,worldWidth:n=Fe.params.worldWidth,worldHeight:f=Fe.params.worldHeight,...x}){let b={u_colorBack:v(t),u_colorFront:v(l),u_shape:qo[i],u_type:mo[c],u_pxSize:m,u_fit:F[s],u_scale:d,u_rotation:u,u_offsetX:y,u_offsetY:g,u_originX:p,u_originY:_,u_worldWidth:n,u_worldHeight:f};return k(A,{...x,speed:o,frame:a,fragmentShader:Xo,uniforms:b})});var Ae={name:"Default",params:{...h,speed:1,frame:0,colorBack:"#000000",colors:["#7300ff","#eba8ff","#00bfff","#2a00ff"],softness:.5,intensity:.5,noise:.25,shape:"corners"}},ni={name:"Wave",params:{...M,speed:1,frame:0,colorBack:"#000a0f",colors:["#c4730b","#bdad5f","#d8ccc7"],softness:.7,intensity:.15,noise:.5,shape:"wave"}},li={name:"Dots",params:{...M,scale:.6,speed:1,frame:0,colorBack:"#0a0000",colors:["#6f0000","#0080ff","#f2ebc9","#33cc33"],softness:1,intensity:1,noise:.7,shape:"dots"}},ci={name:"Truchet",params:{...M,speed:1,frame:0,colorBack:"#0a0000",colors:["#6f2200","#eabb7c","#39b523"],softness:0,intensity:.2,noise:1,shape:"truchet"}},fi={name:"Ripple",params:{...h,scale:.5,speed:1,frame:0,colorBack:"#140a00",colors:["#6f2d00","#88ddae","#2c0b1d"],softness:.5,intensity:.5,noise:.5,shape:"ripple"}},ui={name:"Blob",params:{...h,scale:1.3,speed:1,frame:0,colorBack:"#0f0e18",colors:["#3e6172","#a49b74","#568c50"],softness:0,intensity:.15,noise:.5,shape:"blob"}},fa=[Ae,ni,li,ci,fi,ui],ua=U(function({speed:o=Ae.params.speed,frame:a=Ae.params.frame,colorBack:t=Ae.params.colorBack,colors:l=Ae.params.colors,softness:i=Ae.params.softness,intensity:c=Ae.params.intensity,noise:r=Ae.params.noise,shape:m=Ae.params.shape,fit:s=Ae.params.fit,scale:d=Ae.params.scale,rotation:u=Ae.params.rotation,originX:p=Ae.params.originX,originY:_=Ae.params.originY,offsetX:y=Ae.params.offsetX,offsetY:g=Ae.params.offsetY,worldWidth:n=Ae.params.worldWidth,worldHeight:f=Ae.params.worldHeight,...x}){let b={u_colorBack:v(t),u_colors:l.map(v),u_colorsCount:l.length,u_softness:i,u_intensity:c,u_noise:r,u_shape:Ko[m],u_noiseTexture:le(),u_fit:F[s],u_scale:d,u_rotation:u,u_offsetX:y,u_offsetY:g,u_originX:p,u_originY:_,u_worldWidth:n,u_worldHeight:f};return k(A,{...x,speed:o,frame:a,fragmentShader:jo,uniforms:b})});var H={name:"Default",params:{...h,speed:1,frame:0,scale:.6,colorBack:"#000000",colors:["#0dc1fd","#d915ef","#ff3f2ecc"],roundness:.25,thickness:.1,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,aspectRatio:"auto",softness:.75,intensity:.2,bloom:.25,spots:4,spotSize:.5,pulse:.25,smoke:.3,smokeSize:.6}},mi={name:"Circle",params:{...h,aspectRatio:"square",scale:.6,speed:1,frame:0,colorBack:"#000000",colors:["#0dc1fd","#d915ef","#ff3f2ecc"],roundness:1,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,thickness:0,softness:.75,intensity:.2,bloom:.45,spots:3,spotSize:.4,pulse:.5,smoke:1,smokeSize:0}},pi={name:"Northern lights",params:{...h,speed:.18,scale:1.1,frame:0,colors:["#4c4794","#774a7d","#12694a","#0aff78","#4733cc"],colorBack:"#0c182c",roundness:0,thickness:1,softness:1,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,aspectRatio:"auto",intensity:.1,bloom:.2,spots:4,spotSize:.25,pulse:0,smoke:.32,smokeSize:.5}},di={name:"Solid line",params:{...h,speed:1,frame:0,colors:["#81ADEC"],colorBack:"#00000000",roundness:0,thickness:.05,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,aspectRatio:"auto",softness:0,intensity:0,bloom:.15,spots:4,spotSize:1,pulse:0,smoke:0,smokeSize:0}},ma=[H,mi,pi,di],pa=U(function({speed:o=H.params.speed,frame:a=H.params.frame,colors:t=H.params.colors,colorBack:l=H.params.colorBack,roundness:i=H.params.roundness,thickness:c=H.params.thickness,aspectRatio:r=H.params.aspectRatio,softness:m=H.params.softness,bloom:s=H.params.bloom,intensity:d=H.params.intensity,spots:u=H.params.spots,spotSize:p=H.params.spotSize,pulse:_=H.params.pulse,smoke:y=H.params.smoke,smokeSize:g=H.params.smokeSize,margin:n,marginLeft:f=n??H.params.marginLeft,marginRight:x=n??H.params.marginRight,marginTop:b=n??H.params.marginTop,marginBottom:S=n??H.params.marginBottom,fit:B=H.params.fit,rotation:w=H.params.rotation,scale:C=H.params.scale,originX:V=H.params.originX,originY:O=H.params.originY,offsetX:z=H.params.offsetX,offsetY:E=H.params.offsetY,worldWidth:G=H.params.worldWidth,worldHeight:K=H.params.worldHeight,...X}){let J={u_colorBack:v(l),u_colors:t.map(v),u_colorsCount:t.length,u_roundness:i,u_thickness:c,u_marginLeft:f,u_marginRight:x,u_marginTop:b,u_marginBottom:S,u_aspectRatio:Zo[r],u_softness:m,u_intensity:d,u_bloom:s,u_spots:u,u_spotSize:p,u_pulse:_,u_smoke:y,u_smokeSize:g,u_noiseTexture:le(),u_fit:F[B],u_rotation:w,u_scale:C,u_offsetX:z,u_offsetY:E,u_originX:V,u_originY:O,u_worldWidth:G,u_worldHeight:K};return k(A,{...X,speed:o,frame:a,fragmentShader:Jo,uniforms:J})},I);var te={name:"Default",params:{...h,speed:.5,frame:0,colors:["#ff9d00","#fd4f30","#809bff","#6d2eff","#333aff","#f15cff","#ffd557"],colorBack:"#000000",angle1:0,angle2:0,length:1.1,edges:!1,blur:0,fadeIn:1,fadeOut:.3,gradient:0,density:3,scale:.8}},gi={name:"Glass",params:{...h,rotation:112,speed:1,frame:0,colors:["#00cfff","#ff2d55","#34c759","#af52de"],colorBack:"#ffffff00",angle1:.3,angle2:.3,length:1,edges:!0,blur:.25,fadeIn:.85,fadeOut:.3,gradient:0,density:1.6}},hi={name:"Gradient",params:{...h,speed:.5,frame:0,colors:["#f2ff00","#00000000","#00000000","#5a0283","#005eff"],colorBack:"#8ffff2",angle1:.4,angle2:.4,length:3,edges:!1,blur:.5,fadeIn:1,fadeOut:.39,gradient:.78,density:1.65,scale:1.72,rotation:270,offsetX:.18}},vi={name:"Opening",params:{...h,speed:2,frame:0,colors:["#00ffff"],colorBack:"#570044",angle1:-1,angle2:-1,length:.52,edges:!1,blur:0,fadeIn:0,fadeOut:1,gradient:0,density:2.21,scale:2.32,rotation:360,offsetX:-.3,offsetY:.6}},da=[te,gi,hi,vi],ga=U(function({speed:o=te.params.speed,frame:a=te.params.frame,colors:t=te.params.colors,colorBack:l=te.params.colorBack,angle1:i=te.params.angle1,angle2:c=te.params.angle2,length:r=te.params.length,edges:m=te.params.edges,blur:s=te.params.blur,fadeIn:d=te.params.fadeIn,fadeOut:u=te.params.fadeOut,density:p=te.params.density,gradient:_=te.params.gradient,fit:y=te.params.fit,scale:g=te.params.scale,rotation:n=te.params.rotation,originX:f=te.params.originX,originY:x=te.params.originY,offsetX:b=te.params.offsetX,offsetY:S=te.params.offsetY,worldWidth:B=te.params.worldWidth,worldHeight:w=te.params.worldHeight,...C}){let V={u_colors:t.map(v),u_colorsCount:t.length,u_colorBack:v(l),u_angle1:i,u_angle2:c,u_length:r,u_edges:m,u_blur:s,u_fadeIn:d,u_fadeOut:u,u_density:p,u_gradient:_,u_fit:F[y],u_scale:g,u_rotation:n,u_offsetX:b,u_offsetY:S,u_originX:f,u_originY:x,u_worldWidth:B,u_worldHeight:w};return k(A,{...C,speed:o,frame:a,fragmentShader:$o,uniforms:V})},I);var ue={name:"Default",params:{...h,rotation:270,speed:0,frame:0,colors:["#ffad0a","#6200ff","#e2a3ff","#ff99fd"],positions:2,waveX:1,waveXShift:.6,waveY:1,waveYShift:.21,mixing:.93,grainMixer:0,grainOverlay:0}},xi={name:"Sea",params:{...h,speed:0,frame:0,colors:["#013b65","#03738c","#a3d3ff","#f2faef"],positions:0,waveX:.53,waveXShift:0,waveY:.95,waveYShift:.64,mixing:.5,grainMixer:0,grainOverlay:0}},_i={name:"1960s",params:{...h,speed:0,frame:0,colors:["#000000","#082400","#b1aa91","#8e8c15"],positions:42,waveX:.45,waveXShift:0,waveY:1,waveYShift:0,mixing:0,grainMixer:.37,grainOverlay:.78}},yi={name:"Sunset",params:{...h,speed:0,frame:0,colors:["#264653","#9c2b2b","#f4a261","#ffffff"],positions:0,waveX:.6,waveXShift:.7,waveY:.7,waveYShift:.7,mixing:.5,grainMixer:0,grainOverlay:0}},ha=[ue,_i,yi,xi],va=U(function({speed:o=ue.params.speed,frame:a=ue.params.frame,colors:t=ue.params.colors,positions:l=ue.params.positions,waveX:i=ue.params.waveX,waveXShift:c=ue.params.waveXShift,waveY:r=ue.params.waveY,waveYShift:m=ue.params.waveYShift,mixing:s=ue.params.mixing,grainMixer:d=ue.params.grainMixer,grainOverlay:u=ue.params.grainOverlay,fit:p=ue.params.fit,rotation:_=ue.params.rotation,scale:y=ue.params.scale,originX:g=ue.params.originX,originY:n=ue.params.originY,offsetX:f=ue.params.offsetX,offsetY:x=ue.params.offsetY,worldWidth:b=ue.params.worldWidth,worldHeight:S=ue.params.worldHeight,...B}){let w={u_colors:t.map(v),u_colorsCount:t.length,u_positions:l,u_waveX:i,u_waveXShift:c,u_waveY:r,u_waveYShift:m,u_mixing:s,u_grainMixer:d,u_grainOverlay:u,u_fit:F[p],u_rotation:_,u_scale:y,u_offsetX:f,u_offsetY:x,u_originX:g,u_originY:n,u_worldWidth:b,u_worldHeight:S};return k(A,{...B,speed:o,frame:a,fragmentShader:et,uniforms:w})},I);var $={name:"Default",params:{...h,scale:1,speed:0,frame:0,colorBack:"#000000",colors:["#00bbff","#00ffe1","#ffffff"],radius:.8,focalDistance:.99,focalAngle:0,falloff:.24,mixing:.5,distortion:0,distortionShift:0,distortionFreq:12,grainMixer:0,grainOverlay:0}},bi={name:"Cross Section",params:{...h,scale:1,speed:0,frame:0,colorBack:"#3d348b",colors:["#7678ed","#f7b801","#f18701","#37a066"],radius:1,focalDistance:0,focalAngle:0,falloff:0,mixing:0,distortion:1,distortionShift:0,distortionFreq:12,grainMixer:0,grainOverlay:0}},Si={name:"Radial",params:{...h,scale:1,speed:0,frame:0,colorBack:"#264653",colors:["#9c2b2b","#f4a261","#ffffff"],radius:1,focalDistance:0,focalAngle:0,falloff:0,mixing:1,distortion:0,distortionShift:0,distortionFreq:12,grainMixer:0,grainOverlay:0}},wi={name:"Lo-Fi",params:{...h,speed:0,frame:0,colorBack:"#2e1f27",colors:["#d72638","#3f88c5","#f49d37"],radius:1,focalDistance:0,focalAngle:0,falloff:.9,mixing:.7,distortion:0,distortionShift:0,distortionFreq:12,grainMixer:1,grainOverlay:.5}},xa=[$,wi,bi,Si],_a=U(function({speed:o=$.params.speed,frame:a=$.params.frame,colorBack:t=$.params.colorBack,colors:l=$.params.colors,radius:i=$.params.radius,focalDistance:c=$.params.focalDistance,focalAngle:r=$.params.focalAngle,falloff:m=$.params.falloff,grainMixer:s=$.params.grainMixer,mixing:d=$.params.mixing,distortion:u=$.params.distortion,distortionShift:p=$.params.distortionShift,distortionFreq:_=$.params.distortionFreq,grainOverlay:y=$.params.grainOverlay,fit:g=$.params.fit,rotation:n=$.params.rotation,scale:f=$.params.scale,originX:x=$.params.originX,originY:b=$.params.originY,offsetX:S=$.params.offsetX,offsetY:B=$.params.offsetY,worldWidth:w=$.params.worldWidth,worldHeight:C=$.params.worldHeight,...V}){let O={u_colorBack:v(t),u_colors:l.map(v),u_colorsCount:l.length,u_radius:i,u_focalDistance:c,u_focalAngle:r,u_falloff:m,u_mixing:d,u_distortion:u,u_distortionShift:p,u_distortionFreq:_,u_grainMixer:s,u_grainOverlay:y,u_fit:F[g],u_rotation:n,u_scale:f,u_offsetX:S,u_offsetY:B,u_originX:x,u_originY:b,u_worldWidth:w,u_worldHeight:C};return k(A,{...V,speed:o,frame:a,fragmentShader:ot,uniforms:O})},I);var Y={name:"Default",params:{...h,fit:"contain",scale:.9,speed:0,frame:0,colorBack:"#d3d2ab",colorPaper:"#ffffff",colorShadow:"#cccccc",blending:1,distortion:.75,clip:!1,angle:300,seed:4,roughness:.4,roughnessSize:.5,roughnessRows:0,fiber:.4,fiberSize:.5,folds:.5,foldSizeX:1,foldSizeY:1,foldOffsetX:0,foldOffsetY:0,wrinkles:1,wrinkleSize:.65,crumples:0,crumpleCount:6,drops:.4}},Ci={name:"Creased",params:{...h,fit:"contain",scale:.9,speed:0,frame:0,colorBack:"#d3d2ab",colorPaper:"#ffffff",colorShadow:"#b3b3b3",blending:1,distortion:-.5,clip:!1,angle:60,seed:49,roughness:.4,roughnessSize:.25,roughnessRows:0,fiber:.4,fiberSize:.5,folds:0,foldSizeX:.6,foldSizeY:.89,foldOffsetX:.59,foldOffsetY:1,wrinkles:0,wrinkleSize:.65,crumples:1,crumpleCount:4,drops:0}},Ai={name:"Spread",params:{...h,fit:"contain",scale:.9,speed:0,frame:0,colorBack:"#ffffff00",colorPaper:"#ffffffb5",colorShadow:"#b3b3b3",blending:1,distortion:-.3,clip:!0,angle:236,seed:613,roughness:.15,roughnessSize:.25,roughnessRows:0,fiber:.5,fiberSize:.5,folds:1,foldSizeX:.4,foldSizeY:.89,foldOffsetX:0,foldOffsetY:0,wrinkles:0,wrinkleSize:.65,crumples:0,crumpleCount:9,drops:0}},Bi={name:"Flat",params:{...h,fit:"contain",scale:.9,speed:0,frame:0,colorBack:"#d4cdab",colorPaper:"#ffffffa8",colorShadow:"#b3b3b3",blending:1,distortion:0,clip:!1,angle:0,seed:455,roughness:1,roughnessSize:.5,roughnessRows:.6,fiber:.7,fiberSize:1,folds:0,foldSizeX:0,foldSizeY:.44,foldOffsetX:0,foldOffsetY:0,wrinkles:0,wrinkleSize:0,crumples:0,crumpleCount:6,drops:.2}},ya=[Y,Ai,Ci,Bi],ba=U(function({speed:o=Y.params.speed,frame:a=Y.params.frame,image:t="",colorBack:l=Y.params.colorBack,colorPaper:i=Y.params.colorPaper,colorShadow:c=Y.params.colorShadow,blending:r=Y.params.blending,distortion:m=Y.params.distortion,clip:s=Y.params.clip,angle:d=Y.params.angle,seed:u=Y.params.seed,roughness:p=Y.params.roughness,roughnessSize:_=Y.params.roughnessSize,roughnessRows:y=Y.params.roughnessRows,fiber:g=Y.params.fiber,fiberScale:n,fiberSize:f=n===void 0?Y.params.fiberSize:.2/n,folds:x=Y.params.folds,foldSizeX:b=Y.params.foldSizeX,foldSizeY:S=Y.params.foldSizeY,foldOffsetX:B=Y.params.foldOffsetX,foldOffsetY:w=Y.params.foldOffsetY,wrinkles:C=Y.params.wrinkles,wrinkleSize:V=Y.params.wrinkleSize,crumples:O=Y.params.crumples,foldsNumber:z,crumpleCount:E=z===void 0?Y.params.crumpleCount:z,drops:G=Y.params.drops,fit:K=Y.params.fit,scale:X=Y.params.scale,rotation:J=Y.params.rotation,originX:ne=Y.params.originX,originY:Ue=Y.params.originY,offsetX:Ve=Y.params.offsetX,offsetY:ve=Y.params.offsetY,worldWidth:xe=Y.params.worldWidth,worldHeight:Ee=Y.params.worldHeight,...Oe}){let He=typeof window<"u"&&{u_noiseTexture:le()},R={u_image:t,u_isImage:!!t,u_colorBack:v(l),u_colorPaper:v(i),u_colorShadow:v(c),u_blending:r,u_distortion:m,u_clip:s,u_angle:d,u_seed:u,u_roughness:p,u_roughnessSize:_,u_roughnessRows:y,u_fiber:g,u_fiberSize:f,u_folds:x,u_foldSizeX:b,u_foldSizeY:S,u_foldOffsetX:B,u_foldOffsetY:w,u_wrinkles:C,u_wrinkleSize:V,u_crumples:O,u_crumpleCount:E,u_drops:G,...He,u_fit:F[K],u_scale:X,u_rotation:J,u_offsetX:Ve,u_offsetY:ve,u_originX:ne,u_originY:Ue,u_worldWidth:xe,u_worldHeight:Ee};return k(A,{...Oe,speed:o,frame:a,fragmentShader:tt,mipmaps:["u_image"],uniforms:R})},I);var N={name:"Default",params:{...h,fit:"cover",speed:0,frame:0,colorBack:"#00000000",colorShadow:"#000000",colorHighlight:"#ffffff",shadows:.25,size:.5,angle:0,distortionShape:"prism",highlights:.1,shape:"lines",distortion:.5,shift:0,blur:0,edges:.25,stretch:0,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,grainMixer:0,grainOverlay:0}},ki={name:"Waves",params:{...h,fit:"cover",scale:1.2,speed:0,frame:0,colorBack:"#00000000",colorShadow:"#000000",colorHighlight:"#ffffff",shadows:0,size:.9,angle:0,distortionShape:"contour",highlights:0,shape:"wave",distortion:.5,shift:0,blur:.1,edges:.5,stretch:1,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,grainMixer:0,grainOverlay:.05}},Fi={name:"Abstract",params:{...h,fit:"cover",scale:4,speed:0,frame:0,colorBack:"#00000000",colorShadow:"#000000",colorHighlight:"#ffffff",shadows:0,size:.7,angle:30,distortionShape:"flat",highlights:0,shape:"linesIrregular",distortion:1,shift:0,blur:1,edges:.5,stretch:1,margin:0,marginLeft:0,marginRight:0,marginTop:0,marginBottom:0,grainMixer:.1,grainOverlay:.1}},Ui={name:"Folds",params:{...h,fit:"cover",speed:0,frame:0,colorBack:"#00000000",colorShadow:"#000000",colorHighlight:"#ffffff",shadows:.4,size:.4,angle:0,distortionShape:"cascade",highlights:0,shape:"lines",distortion:.75,shift:0,blur:.25,edges:.5,stretch:0,margin:.1,marginLeft:.1,marginRight:.1,marginTop:.1,marginBottom:.1,grainMixer:0,grainOverlay:0}},Sa=[N,Fi,ki,Ui],wa=U(function({speed:o=N.params.speed,frame:a=N.params.frame,colorBack:t=N.params.colorBack,colorShadow:l=N.params.colorShadow,colorHighlight:i=N.params.colorHighlight,image:c="",shadows:r=N.params.shadows,angle:m=N.params.angle,distortion:s=N.params.distortion,distortionShape:d=N.params.distortionShape,highlights:u=N.params.highlights,shape:p=N.params.shape,shift:_=N.params.shift,blur:y=N.params.blur,edges:g=N.params.edges,margin:n,marginLeft:f=n??N.params.marginLeft,marginRight:x=n??N.params.marginRight,marginTop:b=n??N.params.marginTop,marginBottom:S=n??N.params.marginBottom,grainMixer:B=N.params.grainMixer,grainOverlay:w=N.params.grainOverlay,stretch:C=N.params.stretch,count:V,size:O=V===void 0?N.params.size:Math.pow(1/(V*1.6),1/6)/.7-.5,fit:z=N.params.fit,scale:E=N.params.scale,rotation:G=N.params.rotation,originX:K=N.params.originX,originY:X=N.params.originY,offsetX:J=N.params.offsetX,offsetY:ne=N.params.offsetY,worldWidth:Ue=N.params.worldWidth,worldHeight:Ve=N.params.worldHeight,...ve}){let xe={u_image:c,u_colorBack:v(t),u_colorShadow:v(l),u_colorHighlight:v(i),u_shadows:r,u_size:O,u_angle:m,u_distortion:s,u_shift:_,u_blur:y,u_edges:g,u_stretch:C,u_distortionShape:st[d],u_highlights:u,u_shape:it[p],u_marginLeft:f,u_marginRight:x,u_marginTop:b,u_marginBottom:S,u_grainMixer:B,u_grainOverlay:w,u_fit:F[z],u_scale:E,u_rotation:G,u_offsetX:J,u_offsetY:ne,u_originX:K,u_originY:X,u_worldWidth:Ue,u_worldHeight:Ve};return k(A,{...ve,speed:o,frame:a,fragmentShader:rt,mipmaps:["u_image"],uniforms:xe})});var ge={name:"Default",params:{...h,scale:.8,speed:1,frame:0,colorBack:"#909090",colorHighlight:"#ffffff",highlights:.07,layering:.5,edges:.8,waves:.3,caustic:.1,size:1}},Mi={name:"Abstract",params:{...h,fit:"cover",scale:3,speed:1,frame:0,colorBack:"#909090",colorHighlight:"#ffffff",highlights:0,layering:0,edges:1,waves:1,caustic:.4,size:.15}},Pi={name:"Streaming",params:{...h,fit:"contain",scale:.4,speed:2,frame:0,colorBack:"#909090",colorHighlight:"#ffffff",highlights:0,layering:0,edges:0,waves:.5,caustic:0,size:.5}},Ii={name:"Slow-mo",params:{...h,fit:"cover",scale:1,speed:.1,frame:0,colorBack:"#909090",colorHighlight:"#ffffff",highlights:.4,layering:0,edges:0,waves:0,caustic:.2,size:.7}},Ca=[ge,Ii,Mi,Pi],Aa=U(function({speed:o=ge.params.speed,frame:a=ge.params.frame,colorBack:t=ge.params.colorBack,colorHighlight:l=ge.params.colorHighlight,image:i="",highlights:c=ge.params.highlights,layering:r=ge.params.layering,waves:m=ge.params.waves,edges:s=ge.params.edges,caustic:d=ge.params.caustic,effectScale:u,size:p=u===void 0?ge.params.size:10/9/u-1/9,fit:_=ge.params.fit,scale:y=ge.params.scale,rotation:g=ge.params.rotation,originX:n=ge.params.originX,originY:f=ge.params.originY,offsetX:x=ge.params.offsetX,offsetY:b=ge.params.offsetY,worldWidth:S=ge.params.worldWidth,worldHeight:B=ge.params.worldHeight,...w}){let C={u_image:i,u_colorBack:v(t),u_colorHighlight:v(l),u_highlights:c,u_layering:r,u_waves:m,u_edges:s,u_caustic:d,u_size:p,u_fit:F[_],u_rotation:g,u_scale:y,u_offsetX:x,u_offsetY:b,u_originX:n,u_originY:f,u_worldWidth:S,u_worldHeight:B};return k(A,{...w,speed:o,frame:a,fragmentShader:at,mipmaps:["u_image"],uniforms:C})},I);var he={name:"Default",params:{...h,fit:"cover",speed:0,frame:0,colorFront:"#94ffaf",colorBack:"#000c38",colorHighlight:"#eaff94",type:"8x8",size:2,colorSteps:2,originalColors:!1,inverted:!1}},Ri={name:"Retro",params:{...h,fit:"cover",speed:0,frame:0,colorFront:"#eeeeee",colorBack:"#5452ff",colorHighlight:"#eeeeee",type:"2x2",size:3,colorSteps:1,originalColors:!0,inverted:!1}},Vi={name:"Noise",params:{...h,fit:"cover",speed:0,frame:0,colorFront:"#a2997c",colorBack:"#000000",colorHighlight:"#ededed",type:"random",size:1,colorSteps:1,originalColors:!1,inverted:!1}},zi={name:"Natural",params:{...h,fit:"cover",speed:0,frame:0,colorFront:"#ffffff",colorBack:"#000000",colorHighlight:"#ffffff",type:"8x8",size:2,colorSteps:5,originalColors:!0,inverted:!1}},Ba=[he,Vi,Ri,zi],ka=U(function({speed:o=he.params.speed,frame:a=he.params.frame,colorFront:t=he.params.colorFront,colorBack:l=he.params.colorBack,colorHighlight:i=he.params.colorHighlight,image:c="",type:r=he.params.type,colorSteps:m=he.params.colorSteps,originalColors:s=he.params.originalColors,inverted:d=he.params.inverted,pxSize:u,size:p=u===void 0?he.params.size:u,fit:_=he.params.fit,scale:y=he.params.scale,rotation:g=he.params.rotation,originX:n=he.params.originX,originY:f=he.params.originY,offsetX:x=he.params.offsetX,offsetY:b=he.params.offsetY,worldWidth:S=he.params.worldWidth,worldHeight:B=he.params.worldHeight,...w}){let C={u_image:c,u_colorFront:v(t),u_colorBack:v(l),u_colorHighlight:v(i),u_type:mo[r],u_pxSize:p,u_colorSteps:m,u_originalColors:s,u_inverted:d,u_fit:F[_],u_rotation:g,u_scale:y,u_offsetX:x,u_offsetY:b,u_originX:n,u_originY:f,u_worldWidth:S,u_worldHeight:B};return k(A,{...w,speed:o,frame:a,fragmentShader:nt,uniforms:C})},I);var Q={name:"Default",params:{...h,scale:1,fit:"contain",speed:0,frame:0,spread:.6,bias:1,angle:0,perspective:.1,count:35,dispersion:1,dispersionShift:0,dispersionColor:.6,focusCenter:.8,focusEdges:1,swirl:.35,noise:0,noiseFrequency:.25,noiseOffset:0,lensBulge:0,lensCircle:0,grainMixer:0,grainOverlay:0,imageX:0,imageY:0}},Oi={name:"Fisheye",params:{...h,scale:1,fit:"contain",speed:0,frame:0,spread:.7,bias:1,angle:0,perspective:.75,count:15,dispersion:1,dispersionShift:0,dispersionColor:.7,focusCenter:.9,focusEdges:1,swirl:1,noise:0,noiseFrequency:.25,noiseOffset:0,lensBulge:.95,lensCircle:1,grainMixer:.5,grainOverlay:0,imageX:0,imageY:0}},Di={name:"Duotone",params:{...h,fit:"contain",speed:0,frame:0,spread:.1,bias:0,angle:0,perspective:0,count:2,dispersion:1,dispersionShift:0,dispersionColor:.1,focusCenter:0,focusEdges:0,swirl:0,noise:0,noiseFrequency:.25,noiseOffset:0,lensBulge:0,lensCircle:0,grainMixer:.1,grainOverlay:.3,imageX:0,imageY:0}},Ei={name:"Smoke",params:{...h,scale:1,fit:"contain",speed:0,frame:0,spread:.65,bias:-1,angle:0,perspective:.4,count:50,dispersion:0,dispersionShift:0,dispersionColor:.31,focusCenter:0,focusEdges:.6,swirl:0,noise:1,noiseFrequency:.35,noiseOffset:.3,lensBulge:0,lensCircle:0,grainMixer:0,grainOverlay:0,imageX:0,imageY:0}},Fa=[Q,Oi,Di,Ei],Ua=U(function({speed:o=Q.params.speed,frame:a=Q.params.frame,image:t="",spread:l=Q.params.spread,bias:i=Q.params.bias,angle:c=Q.params.angle,perspective:r=Q.params.perspective,count:m=Q.params.count,dispersion:s=Q.params.dispersion,dispersionShift:d=Q.params.dispersionShift,dispersionColor:u=Q.params.dispersionColor,focusCenter:p=Q.params.focusCenter,focusEdges:_=Q.params.focusEdges,swirl:y=Q.params.swirl,noise:g=Q.params.noise,noiseFrequency:n=Q.params.noiseFrequency,noiseOffset:f=Q.params.noiseOffset,lensBulge:x=Q.params.lensBulge,lensCircle:b=Q.params.lensCircle,grainMixer:S=Q.params.grainMixer,grainOverlay:B=Q.params.grainOverlay,imageX:w=Q.params.imageX,imageY:C=Q.params.imageY,fit:V=Q.params.fit,scale:O=Q.params.scale,rotation:z=Q.params.rotation,originX:E=Q.params.originX,originY:G=Q.params.originY,offsetX:K=Q.params.offsetX,offsetY:X=Q.params.offsetY,worldWidth:J=Q.params.worldWidth,worldHeight:ne=Q.params.worldHeight,...Ue}){let Ve={u_image:t,u_spread:l,u_bias:i,u_angle:c,u_perspective:r,u_count:m,u_dispersion:s,u_dispersionShift:d,u_dispersionColor:u,u_focusCenter:p,u_focusEdges:_,u_swirl:y,u_noise:g,u_noiseFrequency:n,u_noiseOffset:f,u_lensBulge:x,u_lensCircle:b,u_grainMixer:S,u_grainOverlay:B,u_imageX:w,u_imageY:C,u_fit:F[V],u_rotation:z,u_scale:O,u_offsetX:K,u_offsetY:X,u_originX:E,u_originY:G,u_worldWidth:J,u_worldHeight:ne};return k(A,{...Ue,speed:o,frame:a,fragmentShader:lt,mipmaps:["u_image"],uniforms:Ve})},I);var De="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";var Gi=e=>typeof e=="object"&&typeof e.then=="function",Ma=[];function Yi(e,o){if(e===o)return!0;if(!e||!o)return!1;let a=e.length;if(o.length!==a)return!1;for(let t=0;t<a;t++)if(e[t]!==o[t])return!1;return!0}function Ti(e,o=null){o===null&&(o=[e]);for(let t of Ma)if(Yi(o,t.keys)){if(Object.prototype.hasOwnProperty.call(t,"error"))throw t.error;if(Object.prototype.hasOwnProperty.call(t,"response"))return t.response;throw t.promise}let a={keys:o,promise:(Gi(e)?e:e(...o)).then(t=>{a.response=t}).catch(t=>a.error=t)};throw Ma.push(a),a.promise}var ao=(e,o)=>Ti(e,o);var be={name:"Default",params:{...h,scale:.75,speed:1,frame:0,contour:.5,angle:0,noise:0,innerGlow:.5,outerGlow:.5,colorBack:"#000000",colors:["#11206a","#1f3ba2","#2f63e7","#6bd7ff","#ffe679","#ff991e","#ff4c00"]}},Wi={name:"Sepia",params:{...h,scale:.75,speed:.5,frame:0,contour:.5,angle:0,noise:.75,innerGlow:.5,outerGlow:.5,colorBack:"#000000",colors:["#997F45","#ffffff"]}},Pa=[be,Wi],Ia=U(function({speed:o=be.params.speed,frame:a=be.params.frame,image:t="",contour:l=be.params.contour,angle:i=be.params.angle,noise:c=be.params.noise,innerGlow:r=be.params.innerGlow,outerGlow:m=be.params.outerGlow,colorBack:s=be.params.colorBack,colors:d=be.params.colors,suspendWhenProcessingImage:u=!1,fit:p=be.params.fit,offsetX:_=be.params.offsetX,offsetY:y=be.params.offsetY,originX:g=be.params.originX,originY:n=be.params.originY,rotation:f=be.params.rotation,scale:x=be.params.scale,worldHeight:b=be.params.worldHeight,worldWidth:S=be.params.worldWidth,...B}){let w=typeof t=="string"?t:t.src,[C,V]=Ye(De),O;u&&typeof window<"u"?O=ao(()=>So(w).then(E=>URL.createObjectURL(E.blob)),[w,"heatmap"]):O=C,oo(()=>{if(u)return;if(!w){V(De);return}let E,G=!0;return So(w).then(K=>{G&&(E=URL.createObjectURL(K.blob),V(E))}),()=>{G=!1}},[w,u]);let z=Bo(()=>({u_image:O,u_contour:l,u_angle:i,u_noise:c,u_innerGlow:r,u_outerGlow:m,u_colorBack:v(s),u_colors:d.map(v),u_colorsCount:d.length,u_fit:F[p],u_offsetX:_,u_offsetY:y,u_originX:g,u_originY:n,u_rotation:f,u_scale:x,u_worldHeight:b,u_worldWidth:S}),[o,a,l,i,c,r,m,d,s,O,p,_,y,g,n,f,x,b,S]);return k(A,{...B,speed:o,frame:a,fragmentShader:ft,mipmaps:["u_image"],uniforms:z})},I);var se={name:"Default",params:{...h,scale:.6,speed:1,frame:0,colorBack:"#AAAAAC",colorTint:"#ffffff",distortion:.07,repetition:2,shiftRed:.3,shiftBlue:.3,contour:.4,softness:.1,angle:70,shape:"diamond"}},Ni={name:"Noir",params:{...h,scale:.6,speed:1,frame:0,colorBack:"#000000",colorTint:"#606060",softness:.45,repetition:1.5,shiftRed:0,shiftBlue:0,distortion:0,contour:0,angle:90,shape:"diamond"}},Qi={name:"Backdrop",params:{...h,speed:1,frame:0,scale:1,colorBack:"#AAAAAC",colorTint:"#ffffff",softness:.05,repetition:1.5,shiftRed:.3,shiftBlue:.3,distortion:.1,contour:.4,shape:"none",angle:90,worldWidth:0,worldHeight:0}},Li={name:"Stripes",params:{...h,speed:1,frame:0,scale:.6,colorBack:"#000000",colorTint:"#2c5d72",softness:.8,repetition:6,shiftRed:1,shiftBlue:-1,distortion:.4,contour:.4,shape:"circle",angle:0}},Ra=[se,Ni,Qi,Li],Va=U(function({colorBack:o=se.params.colorBack,colorTint:a=se.params.colorTint,speed:t=se.params.speed,frame:l=se.params.frame,image:i="",contour:c=se.params.contour,distortion:r=se.params.distortion,softness:m=se.params.softness,repetition:s=se.params.repetition,shiftRed:d=se.params.shiftRed,shiftBlue:u=se.params.shiftBlue,angle:p=se.params.angle,shape:_=se.params.shape,suspendWhenProcessingImage:y=!1,fit:g=se.params.fit,scale:n=se.params.scale,rotation:f=se.params.rotation,originX:x=se.params.originX,originY:b=se.params.originY,offsetX:S=se.params.offsetX,offsetY:B=se.params.offsetY,worldWidth:w=se.params.worldWidth,worldHeight:C=se.params.worldHeight,...V}){let O=typeof i=="string"?i:i.src,[z,E]=Ye(De),G;y&&typeof window<"u"&&O?G=ao(()=>wo(O).then(X=>URL.createObjectURL(X.pngBlob)),[O,"liquid-metal"]):G=z,oo(()=>{if(y)return;if(!O){E(De);return}let X,J=!0;return wo(O).then(ne=>{J&&(X=URL.createObjectURL(ne.pngBlob),E(X))}),()=>{J=!1}},[O,y]);let K={u_colorBack:v(o),u_colorTint:v(a),u_image:G,u_contour:c,u_distortion:r,u_softness:m,u_repetition:s,u_shiftRed:d,u_shiftBlue:u,u_angle:p,u_isImage:!!i,u_shape:mt[_],u_fit:F[g],u_scale:n,u_rotation:f,u_offsetX:S,u_offsetY:B,u_originX:x,u_originY:b,u_worldWidth:w,u_worldHeight:C};return k(A,{...V,speed:t,frame:l,fragmentShader:ut,mipmaps:["u_image"],uniforms:K})});var ee={name:"Default",params:{...h,fit:"cover",speed:0,frame:0,colorBack:"#f2f1e8",colorFront:"#2b2b2b",size:.5,radius:1.25,contrast:.4,originalColors:!1,inverted:!1,grainMixer:.2,grainOverlay:.2,grainSize:.5,grid:"hex",type:"gooey"}},Hi={name:"LED screen",params:{...h,fit:"cover",speed:0,frame:0,colorBack:"#000000",colorFront:"#29ff7b",size:.5,radius:1.5,contrast:.3,originalColors:!1,inverted:!1,grainMixer:0,grainOverlay:0,grainSize:.5,grid:"square",type:"soft"}},Xi={name:"Mosaic",params:{...h,fit:"cover",speed:0,frame:0,colorBack:"#000000",colorFront:"#b2aeae",size:.6,radius:2,contrast:.01,originalColors:!0,inverted:!1,grainMixer:0,grainOverlay:0,grainSize:.5,grid:"hex",type:"classic"}},qi={name:"Round and square",params:{...h,fit:"cover",speed:0,frame:0,colorBack:"#141414",colorFront:"#ff8000",size:.8,radius:1,contrast:1,originalColors:!1,inverted:!0,grainMixer:.05,grainOverlay:.3,grainSize:.5,grid:"square",type:"holes"}},za=[ee,Hi,Xi,qi],Oa=U(function({speed:o=ee.params.speed,frame:a=ee.params.frame,colorFront:t=ee.params.colorFront,colorBack:l=ee.params.colorBack,image:i="",size:c=ee.params.size,radius:r=ee.params.radius,contrast:m=ee.params.contrast,originalColors:s=ee.params.originalColors,inverted:d=ee.params.inverted,grainMixer:u=ee.params.grainMixer,grainOverlay:p=ee.params.grainOverlay,grainSize:_=ee.params.grainSize,grid:y=ee.params.grid,type:g=ee.params.type,fit:n=ee.params.fit,scale:f=ee.params.scale,rotation:x=ee.params.rotation,originX:b=ee.params.originX,originY:S=ee.params.originY,offsetX:B=ee.params.offsetX,offsetY:w=ee.params.offsetY,worldWidth:C=ee.params.worldWidth,worldHeight:V=ee.params.worldHeight,...O}){let z={u_image:i,u_colorFront:v(t),u_colorBack:v(l),u_size:c,u_radius:r,u_contrast:m,u_originalColors:s,u_inverted:d,u_grainMixer:u,u_grainOverlay:p,u_grainSize:_,u_grid:gt[y],u_type:dt[g],u_fit:F[n],u_rotation:x,u_scale:f,u_offsetX:B,u_offsetY:w,u_originX:b,u_originY:S,u_worldWidth:C,u_worldHeight:V};return k(A,{...O,speed:o,frame:a,fragmentShader:pt,uniforms:z})},I);var W={name:"Default",params:{...h,scale:1,fit:"cover",speed:0,frame:0,colorBack:"#fbfaf5",colorC:"#00b4ff",colorM:"#fc519f",colorY:"#ffd800",colorK:"#231f20",size:.2,contrast:1,softness:1,grainSize:.5,grainMixer:0,grainOverlay:0,gridNoise:.2,floodC:.15,floodM:0,floodY:0,floodK:0,gainC:.3,gainM:0,gainY:.2,gainK:0,type:"ink"}},ji={name:"Drops",params:{...h,scale:1,fit:"cover",speed:0,frame:0,colorBack:"#eeefd7",colorC:"#00b2ff",colorM:"#fc4f4f",colorY:"#ffd900",colorK:"#231f20",size:.88,contrast:1.15,softness:0,grainSize:.01,grainMixer:.05,grainOverlay:.25,gridNoise:.5,floodC:.15,floodM:0,floodY:0,floodK:0,gainC:1,gainM:.44,gainY:-1,gainK:0,type:"ink"}},Ki={name:"Newspaper",params:{...h,scale:1,fit:"cover",speed:0,frame:0,colorBack:"#f2f1e8",colorC:"#7a7a75",colorM:"#7a7a75",colorY:"#7a7a75",colorK:"#231f20",size:.01,contrast:2,softness:.2,grainSize:0,grainMixer:0,grainOverlay:.2,gridNoise:.6,floodC:0,floodM:0,floodY:0,floodK:.1,gainC:-.17,gainM:-.45,gainY:-.45,gainK:0,type:"dots"}},Ji={name:"Vintage",params:{...h,scale:1,fit:"cover",speed:0,frame:0,colorBack:"#fffaf0",colorC:"#59afc5",colorM:"#d8697c",colorY:"#fad85c",colorK:"#2d2824",size:.2,contrast:1.25,softness:.4,grainSize:.5,grainMixer:.15,grainOverlay:.1,gridNoise:.45,floodC:.15,floodM:0,floodY:0,floodK:0,gainC:.3,gainM:0,gainY:.2,gainK:0,type:"sharp"}},Da=[W,ji,Ki,Ji],Ea=U(function({speed:o=W.params.speed,frame:a=W.params.frame,colorBack:t=W.params.colorBack,colorC:l=W.params.colorC,colorM:i=W.params.colorM,colorY:c=W.params.colorY,colorK:r=W.params.colorK,image:m="",size:s=W.params.size,contrast:d=W.params.contrast,softness:u=W.params.softness,grainSize:p=W.params.grainSize,grainMixer:_=W.params.grainMixer,grainOverlay:y=W.params.grainOverlay,gridNoise:g=W.params.gridNoise,floodC:n=W.params.floodC,floodM:f=W.params.floodM,floodY:x=W.params.floodY,floodK:b=W.params.floodK,gainC:S=W.params.gainC,gainM:B=W.params.gainM,gainY:w=W.params.gainY,gainK:C=W.params.gainK,type:V=W.params.type,fit:O=W.params.fit,scale:z=W.params.scale,rotation:E=W.params.rotation,originX:G=W.params.originX,originY:K=W.params.originY,offsetX:X=W.params.offsetX,offsetY:J=W.params.offsetY,worldWidth:ne=W.params.worldWidth,worldHeight:Ue=W.params.worldHeight,...Ve}){let ve={u_image:m,u_noiseTexture:le(),u_colorBack:v(t),u_colorC:v(l),u_colorM:v(i),u_colorY:v(c),u_colorK:v(r),u_size:s,u_contrast:d,u_softness:u,u_grainSize:p,u_grainMixer:_,u_grainOverlay:y,u_gridNoise:g,u_floodC:n,u_floodM:f,u_floodY:x,u_floodK:b,u_gainC:S,u_gainM:B,u_gainY:w,u_gainK:C,u_type:vt[V],u_fit:F[O],u_rotation:E,u_scale:z,u_offsetX:X,u_offsetY:J,u_originX:G,u_originY:K,u_worldWidth:ne,u_worldHeight:Ue};return k(A,{...Ve,speed:o,frame:a,fragmentShader:ht,uniforms:ve})},I);var ae={name:"Default",params:{...h,scale:.6,speed:1,frame:0,colorBack:"#f0efea",colorInner:"#fafaf5",colors:["#333333","#e7e6df"],outerGlow:.55,innerGlow:1,innerDistortion:.8,outerDistortion:.6,offset:0,angle:0,size:.8,shape:"diamond"}},Zi={name:"Fluorescent",params:{...h,scale:.6,speed:1,frame:0,colorBack:"#000000",colorInner:"#000000",colors:["#2fb64c","#cdff61","#ffffff"],outerGlow:0,innerGlow:1,innerDistortion:1,outerDistortion:.8,offset:0,angle:0,size:.8,shape:"diamond"}},$i={name:"Fire",params:{...h,scale:.6,speed:1,frame:0,colorBack:"#000000",colorInner:"#000000",colors:["#fe5b16","#f7ff61","#ffffff"],outerGlow:1,innerGlow:.65,innerDistortion:.6,outerDistortion:.8,offset:0,angle:0,size:.8,shape:"diamond"}},es={name:"Infrared",params:{...h,scale:.6,speed:.5,frame:0,colorBack:"#cd28dc",colorInner:"#00000000",colors:["#ff9900","#fff67a","#dcff52","#00ffbb","#0077ff"],outerGlow:1,innerGlow:1,innerDistortion:1,outerDistortion:1,offset:.2,angle:0,size:1,shape:"diamond"}},Ga=[ae,$i,Zi,es],Ya=U(function({colorBack:o=ae.params.colorBack,colors:a=ae.params.colors,speed:t=ae.params.speed,frame:l=ae.params.frame,image:i="",innerDistortion:c=ae.params.innerDistortion,outerDistortion:r=ae.params.outerDistortion,outerGlow:m=ae.params.outerGlow,innerGlow:s=ae.params.innerGlow,colorInner:d=ae.params.colorInner,offset:u=ae.params.offset,angle:p=ae.params.angle,size:_=ae.params.size,shape:y=ae.params.shape,suspendWhenProcessingImage:g=!1,fit:n=ae.params.fit,scale:f=ae.params.scale,rotation:x=ae.params.rotation,originX:b=ae.params.originX,originY:S=ae.params.originY,offsetX:B=ae.params.offsetX,offsetY:w=ae.params.offsetY,worldWidth:C=ae.params.worldWidth,worldHeight:V=ae.params.worldHeight,...O}){let z=typeof i=="string"?i:i.src,[E,G]=Ye(De),K;g&&typeof window<"u"&&z?K=ao(()=>Co(z).then(J=>URL.createObjectURL(J.pngBlob)),[z,"gemSmoke"]):K=E,oo(()=>{if(g)return;if(!z){G(De);return}let J,ne=!0;return Co(z).then(Ue=>{ne&&(J=URL.createObjectURL(Ue.pngBlob),G(J))}),()=>{ne=!1}},[z,g]);let X={u_colors:a.map(v),u_colorsCount:a.length,u_colorBack:v(o),u_image:K,u_innerDistortion:c,u_outerDistortion:r,u_outerGlow:m,u_innerGlow:s,u_colorInner:v(d),u_offset:u,u_angle:p,u_size:_,u_isImage:!!i,u_shape:yt[y],u_fit:F[n],u_scale:f,u_rotation:x,u_offsetX:B,u_offsetY:w,u_originX:b,u_originY:S,u_worldWidth:C,u_worldHeight:V};return k(A,{...O,speed:t,frame:l,fragmentShader:_t,mipmaps:["u_image"],uniforms:X})},I);var os=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),_o={};for(let[e,o]of Object.entries(ko))if(o&&o.$$paper&&typeof o.type=="function"){let a=ko[e[0].toLowerCase()+e.slice(1)+"Presets"]||[];_o[os(e)]={name:e,fn:o.type,presets:a}}var Na=new Set(["heatmap","liquid-metal","gem-smoke"]);function Ta(e){if(e.naturalWidth<1024&&e.naturalHeight<1024){if(e.naturalWidth<1||e.naturalHeight<1)return;let o=e.naturalWidth/e.naturalHeight;e.width=Math.round(o>1?1024*o:1024),e.height=Math.round(o>1?1024:1024/o)}}function ts(e){return new Promise((o,a)=>{let t=new Image;t.onload=()=>o(t),t.onerror=()=>a(new Error(`hf-paper: could not load image ${String(e).slice(0,80)}`)),t.src=e})}async function as(e){let o={},a=[];for(let[t,l]of Object.entries(e))typeof l=="string"?a.push(ts(l||xo).then(i=>{Ta(i),o[t]=i})):typeof HTMLImageElement<"u"&&l instanceof HTMLImageElement?a.push(l.decode().then(()=>{Ta(l),o[t]=l})):o[t]=l;return await Promise.all(a),o}function rs(e,o,a){let t=document.createElement("canvas"),l=1024/Math.max(o,a);t.width=Math.max(2,Math.round(o*l)),t.height=Math.max(2,Math.round(a*l));let i=t.getContext("2d"),[c,r]=[t.width/2,t.height*.42],m=Math.hypot(t.width,t.height)*.6,s;if(e==="radial"||e==="radial-inv"){s=i.createRadialGradient(c,r,m*.12,c,r,m);let d=e==="radial"?"#ffffff":"#000000",u=e==="radial"?"#000000":"#ffffff";s.addColorStop(0,d),s.addColorStop(.55,d==="#ffffff"?"#d0d0d0":"#303030"),s.addColorStop(1,u)}else if(e==="vertical")s=i.createLinearGradient(0,0,0,t.height),s.addColorStop(0,"#ffffff"),s.addColorStop(1,"#000000");else return i.fillStyle="#808080",i.fillRect(0,0,t.width,t.height),t.toDataURL("image/png");return i.fillStyle=s,i.fillRect(0,0,t.width,t.height),t.toDataURL("image/png")}var Wa=e=>{let o=Math.sin(e*127.1+311.7)*43758.5453123;return o-Math.floor(o)},Le=new Map,ro=0;function is(e,o){if(!o)return e.presets[0]?.params||{};let a=e.presets.find(t=>t.name.toLowerCase()===String(o).toLowerCase());return a||console.warn(`hf-paper: preset "${o}" not found for ${e.name}; have ${e.presets.map(t=>t.name).join(", ")}`),(a||e.presets[0])?.params||{}}function Qa(e,o){let a=e.entry.fn(o);return{fragmentShader:a.props.fragmentShader,uniforms:a.props.uniforms,speed:a.props.speed,frame:a.props.frame}}function La(e,o){return e.frame0+(o-e.t0)*e.speed*1e3}function ss(e,o){let a=e.jitter;if(!a)return null;let t=Math.floor(Math.max(0,o-e.t0)*(a.fps||12)+1e-6),l=a.amount??.004;return{offsetX:(e.params.offsetX||0)+l*(Wa(t)-.5)*2,offsetY:(e.params.offsetY||0)+l*(Wa(t+7919)-.5)*2}}function ns(e){let o={};for(let[a,t]of Object.entries(e))(typeof t=="number"||typeof t=="boolean"||Array.isArray(t))&&(o[a]=t);return o}function St(e,o){if(!e.mount)return;let a=ss(e,o);if(a||e.dirty){let t=a?{...e.params,...a}:e.params;e.mount.setUniformValues(ns(Qa(e,t).uniforms)),e.dirty=!1}e.mount.setFrame(La(e,o))}async function ls(e){let o=(e.dataset.shader||"").toLowerCase(),a=_o[o];if(!a)throw new Error(`hf-paper: unknown shader "${o}". Known: ${Object.keys(_o).join(", ")}`);if(Na.has(o))throw new Error(`hf-paper: "${o}" needs React hooks for image pre-processing; not supported`);let t=e.dataset.params?JSON.parse(e.dataset.params):{},l={...is(a,e.dataset.preset),...t},i=e.getBoundingClientRect(),c=i.width||e.offsetWidth||1080,r=i.height||e.offsetHeight||1920;for(let[y,g]of Object.entries(l))typeof g=="string"&&g.startsWith("gen:")&&(l[y]=rs(g.slice(4),c,r));let m=e.id||`hf-shader-${Le.size}`,s=Le.get(m)||{};Object.assign(s,{id:m,el:e,entry:a,params:l,speed:e.dataset.speed!==void 0?parseFloat(e.dataset.speed):l.speed??1,frame0:e.dataset.frame!==void 0?parseFloat(e.dataset.frame):l.frame??0,t0:parseFloat(e.dataset.t0||"0"),jitter:e.dataset.jitter?JSON.parse(e.dataset.jitter):null,mount:null,dirty:!1}),Le.set(m,s);let d=Qa(s,l),u=await as(d.uniforms),p=parseFloat(e.dataset.minPixelRatio||"1"),_=parseFloat(e.dataset.maxPixelCount||String(1920*1080*4));if(s.mount=new Te(e,d.fragmentShader,u,{preserveDrawingBuffer:!0,antialias:!1},0,La(s,ro),p,_),!s.mount.program)throw new Error(`hf-paper: shader program for ${o} failed to compile`);return s.pending&&(Object.assign(s.params,s.pending),s.pending=null,s.dirty=!0),St(s,ro),s}function wt(e){ro=Math.max(0,Number(e)||0);for(let o of Le.values())St(o,ro)}function Ha(e,o){let a=String(e).replace(/^#/,""),t=Le.get(a);if(t){if(!t.mount){t.pending={...t.pending||{},...o};return}Object.assign(t.params,o),t.dirty=!0,St(t,ro)}}function cs(e,o,a,t,l,i,c="power2.inOut"){let r={...a},m=Object.keys(t);e.fromTo(r,{...a},{...t,duration:i,ease:c,immediateRender:!1,onUpdate:()=>Ha(o,Object.fromEntries(m.map(s=>[s,r[s]])))},l)}var Fo=null;function Ct(e=document){if(Fo)return Fo;let o=[...e.querySelectorAll("[data-shader]")];return o.forEach((a,t)=>{a.id||(a.id=`hf-shader-${t}`),Le.set(a.id,{id:a.id,el:a,mount:null,params:{},pending:null})}),Fo=Promise.all(o.map(a=>ls(a).catch(t=>{throw console.error(t),t}))).then(a=>(wt(ro),document.documentElement.setAttribute("data-hf-paper-ready",String(a.length)),a.length)),Fo}window.addEventListener("hf-seek",e=>wt(e.detail?e.detail.time:0));var Xa={init:Ct,seek:wt,setParams:Ha,tween:cs,shaders:Object.keys(_o).filter(e=>!Na.has(e)),presets:e=>(_o[e]?.presets||[]).map(o=>o.name),layers:Le,version:"0.0.81"};window.HFPaper=Xa;var fs=()=>{window.__hf=window.__hf||{},window.__hf.buildReady=window.__hf.buildReady||{},window.__hf.buildReady["hf-paper"]=Ct()};if(document.readyState==="loading"){window.__hf=window.__hf||{},window.__hf.buildReady=window.__hf.buildReady||{};let e;window.__hf.buildReady["hf-paper"]=new Promise(o=>{e=o}),document.addEventListener("DOMContentLoaded",()=>{Ct().then(e,o=>e(Promise.reject(o)))})}else fs();var Sm=Xa;})();
