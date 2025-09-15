import io

from django.http import FileResponse, HttpResponse
from pandas import DataFrame, ExcelWriter


def dataframe_to_response(df: DataFrame, output_format: str, filename: str):
    if output_format == "csv":
        return DataFrameResponse.as_csv(df, filename)
    elif output_format == "xlsx":
        return DataFrameResponse.as_xlsx(df, filename)
    raise ValueError("Supported output formats: csv, xlsx")


class DataFrameResponse:
    @staticmethod
    def as_csv(df: DataFrame, filename):
        buffer = io.BytesIO()
        df.to_csv(buffer, index=False, mode="wb")
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f"{filename}.csv")

    @staticmethod
    def as_xlsx(df: DataFrame, filename):
        output = io.BytesIO()
        writer = ExcelWriter(output, engine="xlsxwriter")
        df.to_excel(writer, index=False)
        writer.save()
        output.seek(0)
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response = HttpResponse(output.read(), content_type=content_type)
        response["Content-Disposition"] = 'attachment; filename="{}.xlsx"'.format(
            filename
        )
        return response
