// Copyright Unwritten Dao. All Rights Reserved.

#include "WorldCommandClient.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnwrittenDao.h"
#include "WorldSyncSubsystem.h"

namespace
{
	FString JsonToString(const TSharedPtr<FJsonObject>& Object)
	{
		FString Text;
		if (Object.IsValid())
		{
			const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
			FJsonSerializer::Serialize(Object.ToSharedRef(), Writer);
		}
		return Text;
	}

	TSharedPtr<FJsonObject> MakeArguments(const TCHAR* Field, const FString& Value)
	{
		TSharedPtr<FJsonObject> Arguments = MakeShared<FJsonObject>();
		Arguments->SetStringField(Field, Value);
		return Arguments;
	}

	TSharedPtr<FJsonObject> MakeArguments(const TCHAR* Field, int32 Value)
	{
		TSharedPtr<FJsonObject> Arguments = MakeShared<FJsonObject>();
		Arguments->SetNumberField(Field, Value);
		return Arguments;
	}
}

void UWorldCommandClient::Initialize(UWorldSyncSubsystem* InSyncSubsystem)
{
	SyncSubsystem = InSyncSubsystem;
}

FString UWorldCommandClient::MakeIdempotencyKey(const FString& Prefix) const
{
	const FString EffectivePrefix = Prefix.IsEmpty() ? TEXT("ue") : Prefix;
	return EffectivePrefix + TEXT(":") + FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphens);
}

bool UWorldCommandClient::SubmitMove(const FString& ToLocationId, const FString& IdempotencyKey)
{
	return SubmitCommand(TEXT("move"), JsonToString(MakeArguments(TEXT("to_location_id"), ToLocationId)),
		IdempotencyKey, FString());
}

bool UWorldCommandClient::SubmitWait(int32 Ticks, const FString& IdempotencyKey)
{
	return SubmitCommand(TEXT("wait"), JsonToString(MakeArguments(TEXT("ticks"), Ticks)),
		IdempotencyKey, FString());
}

bool UWorldCommandClient::SubmitCultivation(int32 Days, const FString& IdempotencyKey)
{
	return SubmitCommand(TEXT("start_cultivation"), JsonToString(MakeArguments(TEXT("days"), Days)),
		IdempotencyKey, FString());
}

bool UWorldCommandClient::SubmitCommand(
	const FString& CommandType,
	const FString& ArgumentsJson,
	const FString& IdempotencyKey,
	const FString& ActorId)
{
	if (!SyncSubsystem || !SyncSubsystem->LatestSnapshot.bValid)
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("Command: no authoritative snapshot yet"));
		OnCommandRejected.Broadcast(0, TEXT("not_ready"), TEXT("No world snapshot has been received."));
		return false;
	}
	if (bRequestInFlight)
	{
		OnCommandRejected.Broadcast(0, TEXT("busy"), TEXT("Another command is still in flight."));
		return false;
	}

	TSharedPtr<FJsonObject> Arguments;
	if (ArgumentsJson.IsEmpty())
	{
		Arguments = MakeShared<FJsonObject>();
	}
	else
	{
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ArgumentsJson);
		if (!FJsonSerializer::Deserialize(Reader, Arguments) || !Arguments.IsValid())
		{
			OnCommandRejected.Broadcast(0, TEXT("invalid_arguments"), TEXT("ArgumentsJson is not an object."));
			return false;
		}
	}

	const FWorldSnapshotView& Snapshot = SyncSubsystem->LatestSnapshot;
	const FString EffectiveActor = ActorId.IsEmpty() ? Snapshot.PlayerId : ActorId;
	const FString EffectiveKey = IdempotencyKey.IsEmpty()
		? MakeIdempotencyKey(CommandType)
		: IdempotencyKey;

	TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
	Body->SetStringField(TEXT("schema_version"), TEXT("world-command.v1"));
	Body->SetStringField(TEXT("command_id"), FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphens));
	Body->SetStringField(TEXT("idempotency_key"), EffectiveKey);
	Body->SetStringField(TEXT("world_id"), Snapshot.WorldId);
	if (EffectiveActor.IsEmpty())
	{
		Body->SetField(TEXT("actor_id"), MakeShared<FJsonValueNull>());
	}
	else
	{
		Body->SetStringField(TEXT("actor_id"), EffectiveActor);
	}
	Body->SetNumberField(TEXT("issued_tick"), Snapshot.Tick);
	Body->SetNumberField(TEXT("expected_state_version"), Snapshot.StateVersion);
	Body->SetStringField(TEXT("type"), CommandType);
	Body->SetObjectField(TEXT("arguments"), Arguments);
	Body->SetStringField(TEXT("source"), TEXT("player"));

	const FString Url = SyncSubsystem->GetBaseUrl() + TEXT("/v1/commands");
	const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(Url);
	Request->SetVerb(TEXT("POST"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->SetHeader(TEXT("Accept"), TEXT("application/json"));
	Request->SetTimeout(10.0f);
	Request->SetContentAsString(JsonToString(Body));
	Request->OnProcessRequestComplete().BindUObject(
		this, &UWorldCommandClient::HandleCommandResponse);

	bRequestInFlight = true;
	if (!Request->ProcessRequest())
	{
		bRequestInFlight = false;
		OnCommandRejected.Broadcast(0, TEXT("dispatch_failed"), TEXT("HTTP request could not be sent."));
		return false;
	}
	return true;
}

void UWorldCommandClient::HandleCommandResponse(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected)
{
	bRequestInFlight = false;

	if (!bConnected || !Response.IsValid())
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("Command: request did not connect"));
		OnCommandRejected.Broadcast(0, TEXT("network"), TEXT("World server did not respond."));
		return;
	}

	const int32 Status = Response->GetResponseCode();
	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader =
		TJsonReaderFactory<>::Create(Response->GetContentAsString());
	FJsonSerializer::Deserialize(Reader, Root);

	if (Status == EHttpResponseCodes::Conflict)
	{
		FString Code = TEXT("conflict");
		FString Message = TEXT("Stale expected_state_version or idempotency conflict.");
		if (Root.IsValid())
		{
			Root->TryGetStringField(TEXT("code"), Code);
			Root->TryGetStringField(TEXT("message"), Message);
		}
		UE_LOG(LogUnwrittenDao, Warning, TEXT("Command: HTTP 409 (%s), requesting resync"), *Code);
		OnCommandRejected.Broadcast(Status, Code, Message);
		if (SyncSubsystem)
		{
			SyncSubsystem->RequestResync();
		}
		return;
	}

	if (Status != EHttpResponseCodes::Ok || !Root.IsValid())
	{
		FString Code = FString::Printf(TEXT("http_%d"), Status);
		FString Message = TEXT("Command rejected.");
		if (Root.IsValid())
		{
			Root->TryGetStringField(TEXT("code"), Code);
			Root->TryGetStringField(TEXT("message"), Message);
		}
		OnCommandRejected.Broadcast(Status, Code, Message);
		return;
	}

	bool bAccepted = false;
	Root->TryGetBoolField(TEXT("accepted"), bAccepted);
	const int32 NewStateVersion = static_cast<int32>(Root->GetIntegerField(TEXT("state_version")));

	int32 EventCount = 0;
	const TArray<TSharedPtr<FJsonValue>>* Events = nullptr;
	if (Root->TryGetArrayField(TEXT("events"), Events) && Events)
	{
		EventCount = Events->Num();
	}

	if (!bAccepted)
	{
		OnCommandRejected.Broadcast(Status, TEXT("not_accepted"), TEXT("Server did not accept the command."));
		return;
	}

	// Pull the new authoritative snapshot promptly; local state is never advanced here.
	if (SyncSubsystem)
	{
		SyncSubsystem->RequestSnapshotNow();
	}
	OnCommandAccepted.Broadcast(NewStateVersion, EventCount);
}