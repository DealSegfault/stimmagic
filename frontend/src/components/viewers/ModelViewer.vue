<template>
  <div ref="root" class="relative h-full w-full overflow-hidden bg-slideshow-matt" aria-label="3D model preview">
    <div v-if="loading" class="absolute inset-0 z-10 flex items-center justify-center text-xs text-content-muted">
      Chargement du modèle…
    </div>
    <div v-if="error" class="absolute inset-0 z-10 flex items-center justify-center px-6 text-center text-xs text-red-300">
      {{ error }}
    </div>
    <div class="pointer-events-none absolute bottom-3 left-3 z-10 rounded-md bg-black/45 px-2 py-1 text-[11px] text-white/70 backdrop-blur-sm">
      Glisser pour tourner · molette pour zoomer
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

const props = defineProps({
  src: {
    type: String,
    required: true,
  },
})

const root = ref(null)
const loading = ref(true)
const error = ref('')

let scene
let camera
let renderer
let controls
let loader
let model
let animationFrame
let resizeObserver

function disposeObject(object) {
  object?.traverse((child) => {
    if (!child.isMesh) return
    child.geometry?.dispose()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.forEach((material) => {
      if (!material) return
      Object.values(material).forEach((value) => {
        if (value?.isTexture) value.dispose()
      })
      material.dispose()
    })
  })
}

function frameModel(object) {
  const bounds = new THREE.Box3().setFromObject(object)
  const size = bounds.getSize(new THREE.Vector3())
  const center = bounds.getCenter(new THREE.Vector3())
  const maxSize = Math.max(size.x, size.y, size.z, 0.001)
  const distance = maxSize * 2.1

  object.position.sub(center)
  camera.position.set(distance * 0.9, distance * 0.7, distance)
  camera.near = Math.max(0.001, distance / 100)
  camera.far = distance * 100
  camera.updateProjectionMatrix()
  controls.target.set(0, 0, 0)
  controls.update()
}

function loadModel() {
  if (!loader || !scene) return
  loading.value = true
  error.value = ''
  if (model) {
    scene.remove(model)
    disposeObject(model)
    model = null
  }

  loader.load(
    props.src,
    (gltf) => {
      model = gltf.scene
      scene.add(model)
      frameModel(model)
      loading.value = false
    },
    undefined,
    () => {
      loading.value = false
      error.value = 'Impossible de charger cet asset 3D.'
    },
  )
}

function resize() {
  if (!root.value || !renderer || !camera) return
  const width = Math.max(1, root.value.clientWidth)
  const height = Math.max(1, root.value.clientHeight)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height, false)
}

function animate() {
  animationFrame = requestAnimationFrame(animate)
  controls?.update()
  renderer?.render(scene, camera)
}

async function init() {
  await nextTick()
  if (!root.value) return

  scene = new THREE.Scene()
  scene.background = new THREE.Color('#141922')
  camera = new THREE.PerspectiveCamera(35, 1, 0.001, 1000)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.1
  root.value.appendChild(renderer.domElement)

  scene.add(new THREE.HemisphereLight('#e2e8f0', '#172033', 2.2))
  const key = new THREE.DirectionalLight('#ffffff', 3.2)
  key.position.set(4, 6, 5)
  scene.add(key)
  const fill = new THREE.DirectionalLight('#5eead4', 1.1)
  fill.position.set(-4, 2, -3)
  scene.add(fill)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = 0.01
  controls.maxDistance = 100
  controls.enablePan = true
  loader = new GLTFLoader()
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(root.value)
  resize()
  animate()
  loadModel()
}

watch(() => props.src, loadModel)

onMounted(init)

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  controls?.dispose()
  if (model) disposeObject(model)
  renderer?.dispose()
  renderer?.domElement?.remove()
})
</script>
