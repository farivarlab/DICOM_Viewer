"""Native VTK volume renderer, embedded in Qt only when first requested."""
from __future__ import annotations
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class VolumeView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("3D VOLUME    ·    Drag to orbit · wheel to zoom")
        self.label.setObjectName("volumeTitle")
        self.label.setMargin(12)
        self.layout.addWidget(self.label)
        self.placeholder = QLabel("Open a spatial series to render a volume")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.placeholder, 1)
        self.vtk_widget = None
        self.data = None
        self.preset = "CT tissue"
        self.blend = "Composite"
        self.opacity = 1.
        self.crop = 0.
        self._image_ref = None
        self._scalar_range = (0., 1.)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render)
        self.setMinimumSize(200, 160)

    def initialize(self):
        if self.vtk_widget is not None:
            return
        from vtkmodules.qt import QVTKRenderWindowInteractor as qvtk
        qvtk.PyQtImpl = "PySide6"
        from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
        import vtkmodules.vtkRenderingOpenGL2  # register render-window factories
        import vtkmodules.vtkRenderingVolumeOpenGL2
        import vtkmodules.vtkInteractionStyle
        from vtkmodules.vtkRenderingCore import vtkRenderer, vtkVolume, vtkVolumeProperty
        from vtkmodules.vtkRenderingVolumeOpenGL2 import vtkSmartVolumeMapper
        from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
        from vtkmodules.vtkRenderingAnnotation import vtkAnnotatedCubeActor
        from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget

        self.placeholder.hide()
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.layout.addWidget(self.vtk_widget, 1)
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(.025, .04, .065)
        self.renderer.SetBackground2(.06, .095, .14)
        self.renderer.GradientBackgroundOn()
        window = self.vtk_widget.GetRenderWindow()
        window.SetMultiSamples(0)
        window.AddRenderer(self.renderer)
        self.mapper = vtkSmartVolumeMapper()
        self.mapper.SetRequestedRenderModeToDefault()
        self.mapper.SetInteractiveAdjustSampleDistances(True)
        self.mapper.SetInteractiveUpdateRate(20)
        self.prop = vtkVolumeProperty()
        self.prop.SetInterpolationTypeToLinear()
        self.prop.ShadeOn()
        self.prop.SetAmbient(.25)
        self.prop.SetDiffuse(.75)
        self.prop.SetSpecular(.2)
        self.volume = vtkVolume()
        self.volume.SetMapper(self.mapper)
        self.volume.SetProperty(self.prop)
        self.volume.VisibilityOff()
        self.renderer.AddVolume(self.volume)
        self.vtk_widget.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        cube = vtkAnnotatedCubeActor()
        for axis, plus, minus in (("X", "L", "R"), ("Y", "P", "A"), ("Z", "S", "I")):
            getattr(cube, f"Set{axis}PlusFaceText")(plus)
            getattr(cube, f"Set{axis}MinusFaceText")(minus)
        cube.GetCubeProperty().SetColor(.38, .53, .63)
        cube.GetTextEdgesProperty().SetColor(.9, .94, 1)
        self.marker = vtkOrientationMarkerWidget()
        self.marker.SetOrientationMarker(cube)
        self.marker.SetInteractor(window.GetInteractor())
        self.marker.SetViewport(0, 0, .20, .24)
        self.marker.SetEnabled(1)
        self.marker.InteractiveOff()
        self.vtk_widget.Initialize()

    def set_volume(self, data):
        self.data = data
        if not data.mpr_ready:
            self.placeholder.setText(data.geometry_note)
            if self.vtk_widget:
                self.volume.SetVisibility(False)
                self.render()
            return
        self.initialize()
        from vtkmodules.vtkCommonDataModel import vtkImageData
        from vtkmodules.util.numpy_support import numpy_to_vtk
        self._image_ref = np.ascontiguousarray(data.canonical, dtype=np.float32)
        samples = self._image_ref.ravel()[::max(1, self._image_ref.size // 250_000)]
        self._scalar_range = tuple(np.percentile(samples, (2, 98)))
        image = vtkImageData()
        image.SetDimensions(*self._image_ref.shape[::-1])
        image.SetSpacing(*data.canonical_spacing)
        image.SetOrigin(*data.canonical_origin)
        image.GetPointData().SetScalars(numpy_to_vtk(self._image_ref.ravel(), deep=False))
        self.vtk_image = image
        self.mapper.SetInputData(image)
        self.volume.SetVisibility(True)
        if data.series.modality != "CT":
            self.preset = "Scalar"
        self.update_transfer()
        self.set_crop(self.crop)
        self.reset_camera()

    def clear_volume(self):
        """Release a previous series even if the next series is only viewed in 2D."""
        self.render_timer.stop()
        if self.vtk_widget is not None:
            self.volume.VisibilityOff()
            self.mapper.RemoveAllInputs()
        self.data = None
        self.vtk_image = None
        self._image_ref = None
        self._loaded_uid = None

    def schedule_render(self):
        if not self.render_timer.isActive():
            self.render_timer.start(16)

    def update_transfer(self):
        if self.vtk_widget is None or self.data is None or not self.data.mpr_ready:
            return
        from vtkmodules.vtkRenderingCore import vtkColorTransferFunction
        from vtkmodules.vtkCommonDataModel import vtkPiecewiseFunction
        colors = vtkColorTransferFunction()
        opacity = vtkPiecewiseFunction()
        if self.preset == "CT bone":
            stops = [(-1000, (0, 0, 0), 0), (150, (.35, .20, .12), 0),
                     (350, (.72, .51, .31), .07), (1000, (1, .90, .73), .65), (2500, (1, 1, 1), .95)]
        elif self.preset == "CT tissue":
            stops = [(-1000, (0, 0, 0), 0), (-200, (.3, .1, .12), 0), (40, (.8, .36, .25), .025),
                     (180, (.98, .68, .42), .12), (600, (1, .9, .72), .48), (2200, (1, 1, 1), .85)]
        elif self.preset == "CT lung":
            stops = [(-1000, (0, 0, 0), 0), (-850, (.2, .4, .7), .06), (-550, (.5, .75, 1), .20),
                     (-200, (.9, .65, .5), .01), (500, (1, 1, .9), .1), (2000, (1, 1, 1), .6)]
        else:
            lo, hi = self._scalar_range
            hi = max(hi, lo + 1)
            stops = [(lo, (0, 0, 0), 0), (lo + .3 * (hi - lo), (.3, .25, .5), .01),
                     (lo + .65 * (hi - lo), (.9, .6, .3), .12), (hi, (1, .95, .85), .6)]
        for value, color, alpha in stops:
            colors.AddRGBPoint(value, *color)
            opacity.AddPoint(value, min(1, alpha * self.opacity))
        self.prop.SetColor(colors)
        self.prop.SetScalarOpacity(opacity)
        self.prop.SetScalarOpacityUnitDistance(min(self.data.canonical_spacing))
        self.prop.SetShade(self.blend == "Composite")
        if self.blend == "MIP":
            self.mapper.SetBlendModeToMaximumIntensity()
        elif self.blend == "MinIP":
            self.mapper.SetBlendModeToMinimumIntensity()
        else:
            self.mapper.SetBlendModeToComposite()
        self.schedule_render()

    def set_crop(self, fraction):
        self.crop = fraction
        if self.vtk_widget is None or self.data is None or not self.data.mpr_ready:
            return
        bounds = list(self.vtk_image.GetBounds())
        bounds[3] -= (bounds[3] - bounds[2]) * self.crop
        self.mapper.SetCroppingRegionPlanes(*bounds)
        self.mapper.SetCroppingRegionFlagsToSubVolume()
        self.mapper.SetCropping(self.crop > 0)
        self.schedule_render()

    def reset_camera(self):
        if self.vtk_widget is None:
            return
        self.renderer.ResetCamera()
        center = self.volume.GetCenter()
        camera = self.renderer.GetActiveCamera()
        distance = camera.GetDistance()
        camera.SetPosition(center[0], center[1] - distance, center[2] + distance * .18)
        camera.SetFocalPoint(*center)
        camera.SetViewUp(0, 0, 1)
        camera.Azimuth(20)
        self.renderer.ResetCameraClippingRange()
        self.render()

    def render(self):
        if self.vtk_widget is not None and self.isVisible():
            self.vtk_widget.GetRenderWindow().Render()

    def capture(self):
        if self.vtk_widget is None:
            return None
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
        from vtkmodules.util.numpy_support import vtk_to_numpy
        from PySide6.QtGui import QImage
        self.vtk_widget.GetRenderWindow().Render()
        capture = vtkWindowToImageFilter()
        capture.SetInput(self.vtk_widget.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        image = capture.GetOutput()
        w, h, _ = image.GetDimensions()
        array = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(h, w, -1)[::-1].copy()
        return QImage(array.data, w, h, array.strides[0], QImage.Format.Format_RGB888).copy()

    def shutdown(self):
        self.render_timer.stop()
        if self.vtk_widget is not None:
            self.marker.SetEnabled(0)
            self.vtk_widget.Finalize()
